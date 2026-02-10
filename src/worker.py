"""Background worker: processes pending check_tasks (load docx, run analysis, save result)."""

import logging
import os
import time
from pathlib import Path
from typing import cast

from dotenv import load_dotenv

from .agent import analyze_tests_auto, MAX_INPUT_CHARS
from .db import (
    claim_next_pending_task,
    get_task,
    init_db,
    insert_check_result,
    update_check_result_pdfs,
    update_task_completed,
    update_task_error,
)
from .doc_loader import load_document
from .pdf_generator import generate_pdf
from .translator import get_report_in_language

load_dotenv()
logger = logging.getLogger(__name__)
POLL_INTERVAL = 5


def _output_root() -> Path:
    # Keep default compatible with README/CLI
    return Path(os.getenv("AICHECK_OUTPUT_DIR", "output"))


def process_one_task() -> bool:
    """Claim and process one pending task. Returns True if a task was processed."""
    init_db()
    task_id = claim_next_pending_task()
    if not task_id:
        return False
    task = get_task(task_id)
    if not task or task["status"] != "in_progress":
        return False
    file_path = task.get("file_path")
    file_name = task.get("file_name") or "document.docx"
    if not file_path or not os.path.isfile(file_path):
        update_task_error(task_id, "Файл не найден: " + (file_path or ""))
        return True
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        update_task_error(task_id, "OPENAI_API_KEY не задан")
        return True
    try:
        file_text, detected_lang = load_document(file_path)
        if not file_text.strip():
            update_task_error(task_id, "Документ пуст или текст не извлечён")
            return True
        result = analyze_tests_auto(file_text, detected_lang, api_key)
        assessment = result["assessment"]
        usage = result.get("usage") or {}
        risk_level = assessment.get("risk_level", "N/A")
        row_id = insert_check_result(
            detected_language=detected_lang,
            risk_level=risk_level,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            assessment=assessment,
            file_name=file_name,
        )

        # Generate PDFs (best-effort) and store file paths
        pdf_paths: dict[str, str] = {}
        out_root = _output_root()
        try:
            for lang in ("ru", "kk", "en"):
                report_text = get_report_in_language(
                    assessment, lang, api_key, detected_lang
                )
                lang_dir = out_root / f"{lang}_pdf"
                lang_dir.mkdir(parents=True, exist_ok=True)
                # ASCII-safe filename (avoid Cyrillic issues on some setups)
                out_file = lang_dir / f"conclusion_{row_id}.pdf"
                generate_pdf(report_text, out_file, assessment_data=assessment)
                pdf_paths[lang] = str(out_file)
        except Exception as e:
            logger.warning("PDF generation failed for task %s: %s", task_id, e)

        if pdf_paths:
            update_check_result_pdfs(
                row_id,
                pdf_ru_path=pdf_paths.get("ru"),
                pdf_kk_path=pdf_paths.get("kk"),
                pdf_en_path=pdf_paths.get("en"),
            )

        update_task_completed(
            task_id=task_id,
            result_id=row_id,
            detected_language=detected_lang,
            risk_level=risk_level,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )
        logger.info("Task %s completed, result_id=%s", task_id, row_id)
        return True
    except Exception as e:
        logger.exception("Task %s failed", task_id)
        update_task_error(task_id, str(e))
        return True


def worker_loop() -> None:
    """Run forever: poll for pending tasks and process them."""
    while True:
        try:
            process_one_task()
        except Exception as e:
            logger.exception("Worker iteration failed: %s", e)
        time.sleep(POLL_INTERVAL)


def start_worker_thread() -> None:
    """Start the background worker in a daemon thread (call once at app startup)."""
    import threading
    if getattr(start_worker_thread, "_started", False):
        return
    start_worker_thread._started = True
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()
    logger.info("Background check worker thread started")
