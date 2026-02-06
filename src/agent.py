"""OpenAI agent for test quality assessment."""

import json
import logging
import time
from openai import OpenAI, RateLimitError

from .doc_loader import split_into_question_chunks
from .prompts import SYSTEM_MESSAGE, USER_MESSAGE_TEMPLATE, JSON_SCHEMA

logger = logging.getLogger(__name__)

# Лимит для одного вызова API (учитываем TPM 30k: input + output < 30k токенов)
MAX_INPUT_CHARS = 50_000
# Размер чанка при разбивке (≈15k токенов input + 8k output < 30k TPM)
MAX_CHUNKED_CHARS = 18_000

REQUIRED_KEYS = [
    "overall_assessment",
    "risk_level",
    "major_findings",
    "quality_scores",
    "common_error_patterns",
    "action_plan",
    "spot_check",
]


def _call_api(client: OpenAI, user_message: str, attempt: int, use_json_object: bool = False):
    """Call OpenAI API with structured output or json_object."""
    fmt = {"type": "json_object"} if use_json_object else JSON_SCHEMA
    return client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": user_message},
        ],
        response_format=fmt,
        max_tokens=8000,
    )


def analyze_tests(
    file_text: str,
    detected_language: str,
    api_key: str | None = None,
    *,
    chunk_context: str | None = None,
) -> dict:
    """
    Call OpenAI API to analyze test bank quality.
    Returns parsed JSON assessment.
    file_text must be within MAX_INPUT_CHARS (caller is responsible for chunking).
    chunk_context: optional note like "Чанк 2 из 5, вопросы 21-40" for chunked mode.
    """
    if chunk_context:
        file_text = f"[{chunk_context}]\n\n{file_text}"

    client = OpenAI(api_key=api_key)
    user_message = USER_MESSAGE_TEMPLATE.format(
        detected_language=detected_language,
        file_text=file_text,
    )

    for attempt in range(5):  # 5 attempts to allow retries on rate limit
        try:
            try:
                response = _call_api(client, user_message, attempt)
            except Exception as api_err:
                if "json_schema" in str(api_err).lower() or "schema" in str(api_err).lower():
                    logger.warning("Structured output failed, falling back to JSON mode: %s", api_err)
                    response = _call_api(client, user_message, attempt, use_json_object=True)
                else:
                    raise

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from API")

            data = json.loads(content)
            _validate_assessment(data)
            return data

        except RateLimitError as e:
            wait = 60 * (attempt + 1)  # 60, 120, 180, 240 sec
            logger.warning("Rate limit (429), ждём %d сек перед повтором...", wait)
            time.sleep(wait)
            if attempt >= 4:
                raise
        except json.JSONDecodeError as e:
            logger.warning("JSON parse error (attempt %d): %s", attempt + 1, e)
            if attempt < 2:
                content = content or ""
                content = _extract_json_from_text(content)
                try:
                    data = json.loads(content)
                    _validate_assessment(data)
                    return data
                except (json.JSONDecodeError, ValueError):
                    continue
            raise
        except (KeyError, IndexError) as e:
            logger.warning("Response structure error (attempt %d): %s", attempt + 1, e)
            if attempt >= 2:
                raise

    raise RuntimeError("Failed to get valid assessment after retries")


def _extract_json_from_text(text: str) -> str:
    """Try to extract JSON from markdown code block or raw text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text


def _validate_assessment(data: dict) -> None:
    """Validate that all required keys and nested structures exist."""
    for key in REQUIRED_KEYS:
        if key not in data:
            raise ValueError(f"Missing required key: {key}")

    qs = data.get("quality_scores", {})
    required_scores = [
        "clarity",
        "single_best_answer",
        "distractors",
        "no_clues",
        "language",
        "structure_consistency",
    ]
    for s in required_scores:
        if s not in qs:
            raise ValueError(f"Missing quality_score: {s}")

    sc = data.get("spot_check", {})
    if "sample_size" not in sc or "suspicious_question_numbers" not in sc:
        raise ValueError("spot_check must have sample_size and suspicious_question_numbers")


def _merge_assessments(assessments: list[tuple[dict, int]]) -> dict:
    """
    Merge multiple assessment dicts from chunked processing.
    assessments: list of (assessment_dict, question_offset) where offset is 1-based start for that chunk.
    """
    if not assessments:
        raise ValueError("No assessments to merge")
    if len(assessments) == 1:
        return assessments[0][0].copy()

    RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

    merged: dict = {
        "overall_assessment": "",
        "risk_level": "LOW",
        "major_findings": [],
        "quality_scores": {},
        "common_error_patterns": [],
        "action_plan": [],
        "spot_check": {"sample_size": 0, "suspicious_question_numbers": []},
    }

    seen_titles: set[str] = set()
    seen_patterns: set[str] = set()
    total_sample = 0
    step_counter = 1

    for data, offset in assessments:
        # overall_assessment: concatenate with separator
        part = data.get("overall_assessment", "").strip()
        if part:
            merged["overall_assessment"] += ("" if not merged["overall_assessment"] else "\n\n---\n\n") + part

        # risk_level: take maximum
        r = data.get("risk_level", "LOW")
        if RISK_ORDER.get(r, 0) > RISK_ORDER.get(merged["risk_level"], 0):
            merged["risk_level"] = r

        # major_findings: merge, dedupe by title
        for f in data.get("major_findings", []):
            t = f.get("title", "")
            if t and t not in seen_titles:
                seen_titles.add(t)
                merged["major_findings"].append(f)

        # quality_scores: average
        qs = data.get("quality_scores", {})
        for k, v in qs.items():
            if isinstance(v, (int, float)):
                merged["quality_scores"][k] = merged["quality_scores"].get(k, 0) + v
        total_sample += 1

        # common_error_patterns: merge, dedupe by pattern
        for ep in data.get("common_error_patterns", []):
            p = ep.get("pattern", "")
            if p and p not in seen_patterns:
                seen_patterns.add(p)
                merged["common_error_patterns"].append(ep)

        # action_plan: merge, renumber steps
        for ap in data.get("action_plan", []):
            ap_copy = ap.copy()
            ap_copy["step"] = step_counter
            step_counter += 1
            merged["action_plan"].append(ap_copy)

        # spot_check: merge, adjust question numbers by offset
        sc = data.get("spot_check", {})
        merged["spot_check"]["sample_size"] += sc.get("sample_size", 0)
        for sq in sc.get("suspicious_question_numbers", []):
            num = sq.get("number", 0)
            if isinstance(num, (int, float)):
                num = int(num) + offset - 1  # offset is 1-based start of chunk
            merged["spot_check"]["suspicious_question_numbers"].append({
                "number": num,
                "reason": sq.get("reason", ""),
            })

    # Average quality_scores
    n = total_sample or 1
    for k in merged["quality_scores"]:
        merged["quality_scores"][k] = round(merged["quality_scores"][k] / n, 1)

    return merged


def analyze_tests_chunked(
    file_text: str,
    detected_language: str,
    api_key: str | None = None,
) -> dict:
    """
    Analyze large document by splitting into question chunks and merging results.
    """
    chunks = split_into_question_chunks(file_text, MAX_CHUNKED_CHARS)
    if not chunks:
        chunks = [(file_text[:MAX_CHUNKED_CHARS], 1)]

    logger.info("Чанковая обработка: %d чанков", len(chunks))
    assessments: list[tuple[dict, int]] = []

    for i, (chunk_text, offset) in enumerate(chunks):
        if i > 0:
            # Пауза между чанками, чтобы не превысить TPM
            time.sleep(65)
        ctx = f"Чанк {i + 1} из {len(chunks)}, вопросы с №{offset}"
        logger.info("Анализ %s...", ctx)
        data = analyze_tests(chunk_text, detected_language, api_key, chunk_context=ctx)
        assessments.append((data, offset))

    return _merge_assessments(assessments)


def analyze_tests_auto(
    file_text: str,
    detected_language: str,
    api_key: str | None = None,
) -> dict:
    """
    Analyze test bank. Uses single API call if within limit, else chunked processing.
    """
    if len(file_text) <= MAX_INPUT_CHARS:
        return analyze_tests(file_text, detected_language, api_key)
    logger.info("Документ большой (%d символов), используется чанковая обработка", len(file_text))
    return analyze_tests_chunked(file_text, detected_language, api_key)
