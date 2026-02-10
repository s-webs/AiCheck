"""Format assessment JSON to report text and translate to KK/EN."""

import logging
import re
from openai import OpenAI

logger = logging.getLogger(__name__)


def json_to_report_text(data: dict) -> str:
    """
    Convert assessment JSON to formatted report text (Russian).
    """
    lines: list[str] = []

    lines.append("ЗАКЛЮЧЕНИЕ")
    lines.append("по результатам экспертизы банка тестовых заданий")
    lines.append("")
    lines.append("=" * 60)
    lines.append("")

    lines.append("1. ОБЩАЯ ОЦЕНКА")
    lines.append("-" * 40)
    lines.append(data.get("overall_assessment", ""))
    lines.append("")

    risk = data.get("risk_level", "N/A")
    lines.append(f"Уровень риска: {risk}")
    lines.append("")

    lines.append("2. ОСНОВНЫЕ ВЫВОДЫ")
    lines.append("-" * 40)
    for i, f in enumerate(data.get("major_findings", []), 1):
        sev = f.get("severity", "")
        title = f.get("title", "")
        details = f.get("details", "")
        lines.append(f"{i}. [{sev}] {title}")
        lines.append(f"   {details}")
        lines.append("")
    lines.append("")

    lines.append("3. ОЦЕНКИ КАЧЕСТВА (0–10)")
    lines.append("-" * 40)
    qs = data.get("quality_scores", {})
    labels = {
        "clarity": "Ясность формулировок",
        "single_best_answer": "Один лучший ответ",
        "distractors": "Качество дистракторов",
        "no_clues": "Отсутствие подсказок",
        "language": "Языковая корректность",
        "structure_consistency": "Структурная согласованность",
        "difficulty_balance": "Баланс сложности",
        "content_accuracy": "Точность содержания",
        "formatting_quality": "Качество форматирования",
        "answer_key_quality": "Качество ключа ответов",
    }
    for key, label in labels.items():
        val = qs.get(key, "—")
        lines.append(f"  {label}: {val}")
    lines.append("")
    
    lines.append("4. АНАЛИТИЧЕСКИЕ ГРАФИКИ")
    lines.append("-" * 40)
    lines.append("Графики представлены ниже.")
    lines.append("")

    lines.append("5. ТИПОВЫЕ ОШИБКИ И ШАБЛОНЫ ИСПРАВЛЕНИЯ")
    lines.append("-" * 40)
    for i, ep in enumerate(data.get("common_error_patterns", []), 1):
        lines.append(f"{i}. Паттерн: {ep.get('pattern', '')}")
        lines.append(f"   Почему плохо: {ep.get('why_bad', '')}")
        lines.append(f"   Как исправить: {ep.get('how_to_fix', '')}")
        lines.append(f"   Пример: {ep.get('example_rewrite_template', '')}")
        lines.append("")
    lines.append("")

    lines.append("6. ПЛАН ДЕЙСТВИЙ (ЮКМА)")
    lines.append("-" * 40)
    for ap in data.get("action_plan", []):
        step = ap.get("step", "")
        action = ap.get("action", "")
        owner = ap.get("owner", "")
        result = ap.get("expected_result", "")
        lines.append(f"Шаг {step}. {action}")
        lines.append(f"   Ответственный: {owner}")
        lines.append(f"   Ожидаемый результат: {result}")
        lines.append("")
    lines.append("")

    lines.append("7. ВЫБОРОЧНАЯ ПРОВЕРКА")
    lines.append("-" * 40)
    sc = data.get("spot_check", {})
    sample_size = sc.get("sample_size", 0)
    lines.append(f"Размер выборки: {sample_size} вопросов")
    lines.append("")
    for sq in sc.get("suspicious_question_numbers", []):
        num = sq.get("number", "")
        reason = sq.get("reason", "")
        lines.append(f"  Вопрос №{num}: {reason}")
    lines.append("")

    return "\n".join(lines)


def translate_report(text: str, target_lang: str, api_key: str | None = None) -> str:
    """
    Translate report text to target language (kk or en).
    """
    if target_lang.lower() == "ru":
        return text

    lang_names = {"kk": "казахский", "en": "английский"}
    lang_name = lang_names.get(target_lang.lower(), "английский")

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"Ты — профессиональный переводчик. Переведи следующий официальный отчёт по качеству тестов на {lang_name}. Сохрани структуру, нумерацию, заголовки и форматирование. Не добавляй пояснений.",
            },
            {"role": "user", "content": text},
        ],
    )
    return response.choices[0].message.content or text


def _is_english_text(text: str) -> bool:
    """
    Detect if text appears to be in English (fallback check).
    Checks for common English phrases and patterns.
    """
    if not text or len(text.strip()) < 20:
        return False
    # Check first 500 chars for English patterns
    sample = text[:500].strip()
    english_patterns = [
        r"^The\s+\w+",  # "The overall", "The test"
        r"^This\s+\w+",  # "This assessment"
        r"^Overall\s+",  # "Overall quality"
        r"^In\s+",  # "In conclusion"
        r"\bthe\s+test\s+bank\b",  # "the test bank"
        r"\bassessment\s+of\b",  # "assessment of"
        r"\bquality\s+of\s+the\b",  # "quality of the"
        r"\bare\s+critical\b",  # "are critical"
        r"\bneed\s+improvement\b",  # "need improvement"
        r"\bhowever\s*,",  # "However,"
        r"\btherefore\s*,",  # "Therefore,"
    ]
    # Check if any English pattern matches
    has_english_pattern = any(re.search(pattern, sample, re.IGNORECASE) for pattern in english_patterns)
    
    # Also check for Cyrillic characters - if found, it's likely not English
    has_cyrillic = bool(re.search(r'[А-Яа-яЁё]', sample))
    has_kazakh = bool(re.search(r'[ӘәҒғҚқҢңӨөҰұҮүҺһ]', sample))
    
    # If has Cyrillic or Kazakh, it's not English
    if has_cyrillic or has_kazakh:
        return False
    
    return has_english_pattern


def _translate_assessment_to_russian(data: dict, api_key: str | None = None) -> dict:
    """
    Translate assessment JSON from English to Russian if needed.
    Returns a new dict with translated text fields.
    """
    client = OpenAI(api_key=api_key)
    
    # Build translation prompt
    text_fields = []
    text_fields.append(f"overall_assessment: {data.get('overall_assessment', '')}")
    
    for i, f in enumerate(data.get("major_findings", []), 1):
        text_fields.append(f"major_findings[{i}].title: {f.get('title', '')}")
        text_fields.append(f"major_findings[{i}].details: {f.get('details', '')}")
    
    for i, ep in enumerate(data.get("common_error_patterns", []), 1):
        text_fields.append(f"common_error_patterns[{i}].pattern: {ep.get('pattern', '')}")
        text_fields.append(f"common_error_patterns[{i}].why_bad: {ep.get('why_bad', '')}")
        text_fields.append(f"common_error_patterns[{i}].how_to_fix: {ep.get('how_to_fix', '')}")
        text_fields.append(f"common_error_patterns[{i}].example_rewrite_template: {ep.get('example_rewrite_template', '')}")
    
    for i, ap in enumerate(data.get("action_plan", []), 1):
        text_fields.append(f"action_plan[{i}].action: {ap.get('action', '')}")
        text_fields.append(f"action_plan[{i}].expected_result: {ap.get('expected_result', '')}")
    
    for i, sq in enumerate(data.get("spot_check", {}).get("suspicious_question_numbers", []), 1):
        text_fields.append(f"spot_check.suspicious_question_numbers[{i}].reason: {sq.get('reason', '')}")
    
    prompt_text = "\n".join(text_fields)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Ты — профессиональный переводчик. Переведи следующие текстовые поля из JSON-отчёта с английского на русский. Верни ТОЛЬКО переведённые значения в том же формате (по одному на строку, с префиксом поля). Сохрани структуру и технические термины где уместно.",
                },
                {"role": "user", "content": prompt_text},
            ],
        )
        
        translated_text = response.choices[0].message.content or ""
        if not translated_text:
            return data
        
        # Parse translated fields back into dict
        result = data.copy()
        lines = translated_text.strip().split("\n")
        
        for line in lines:
            if ":" not in line:
                continue
            key_part, value = line.split(":", 1)
            value = value.strip()
            
            # Parse nested keys
            if key_part.startswith("overall_assessment"):
                result["overall_assessment"] = value
            elif key_part.startswith("major_findings["):
                match = re.match(r"major_findings\[(\d+)\]\.(title|details)", key_part)
                if match:
                    idx = int(match.group(1)) - 1
                    field = match.group(2)
                    if idx < len(result.get("major_findings", [])):
                        result["major_findings"][idx][field] = value
            elif key_part.startswith("common_error_patterns["):
                match = re.match(r"common_error_patterns\[(\d+)\]\.(pattern|why_bad|how_to_fix|example_rewrite_template)", key_part)
                if match:
                    idx = int(match.group(1)) - 1
                    field = match.group(2)
                    if idx < len(result.get("common_error_patterns", [])):
                        result["common_error_patterns"][idx][field] = value
            elif key_part.startswith("action_plan["):
                match = re.match(r"action_plan\[(\d+)\]\.(action|expected_result)", key_part)
                if match:
                    idx = int(match.group(1)) - 1
                    field = match.group(2)
                    if idx < len(result.get("action_plan", [])):
                        result["action_plan"][idx][field] = value
            elif key_part.startswith("spot_check.suspicious_question_numbers["):
                match = re.match(r"spot_check\.suspicious_question_numbers\[(\d+)\]\.reason", key_part)
                if match:
                    idx = int(match.group(1)) - 1
                    sq_list = result.get("spot_check", {}).get("suspicious_question_numbers", [])
                    if idx < len(sq_list):
                        sq_list[idx]["reason"] = value
        
        return result
    except Exception as e:
        logger.warning("Failed to translate assessment to Russian: %s", e)
        return data


def get_report_in_language(
    data: dict, lang: str, api_key: str | None = None, detected_language: str = "RU"
) -> str:
    """
    Get report text in the specified language (ru, kk, en).
    
    Args:
        data: Assessment JSON dict
        lang: Target language (ru, kk, en)
        api_key: OpenAI API key for translation
        detected_language: Original language of the test document (RU, KK, EN)
    """
    # Always check if assessment is in English and translate to Russian first
    # Tests are analyzed in their original language, but conclusion must be translated
    overall_assessment = data.get("overall_assessment", "")
    if _is_english_text(overall_assessment):
        logger.info("Detected English text in assessment, translating to Russian first...")
        data = _translate_assessment_to_russian(data, api_key)
    
    # Generate Russian text from assessment
    ru_text = json_to_report_text(data)
    
    # Return Russian if requested
    if lang.lower() == "ru":
        return ru_text
    
    # Translate to target language (kk or en)
    logger.info("Translating report to %s...", lang.upper())
    return translate_report(ru_text, lang, api_key)
