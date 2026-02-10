#!/usr/bin/env python3
"""CLI for AiCheck - AI agent for test quality assessment."""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.agent import analyze_tests_auto
from src.doc_loader import load_document
from src.pdf_generator import generate_pdf
from src.translator import get_report_in_language

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Проверка качества тестовых заданий через ИИ-агент"
    )
    parser.add_argument(
        "docx_path",
        type=Path,
        help="Путь к Word-файлу (.docx) с тестами",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("./output"),
        help="Каталог для PDF-отчётов (по умолчанию: ./output)",
    )
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set. Create .env from .env.example")
        return 1

    docx_path = args.docx_path.resolve()
    if not docx_path.exists():
        logger.error("Файл не найден: %s", docx_path)
        return 1
    if docx_path.suffix.lower() != ".docx":
        logger.error("Ожидается файл .docx: %s", docx_path)
        return 1

    output_dir = args.output_dir.resolve()
    ru_dir = output_dir / "ru_pdf"
    kk_dir = output_dir / "kk_pdf"
    en_dir = output_dir / "en_pdf"
    for d in (ru_dir, kk_dir, en_dir):
        d.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Загрузка документа: %s", docx_path)
        file_text, detected_lang = load_document(docx_path)
        logger.info("Язык документа: %s, символов: %d", detected_lang, len(file_text))

        if not file_text.strip():
            logger.error("Документ пуст или текст не извлечён")
            return 1

        logger.info("Анализ через OpenAI...")
        assessment = analyze_tests_auto(file_text, detected_lang, api_key)
        logger.info("Анализ завершён. risk_level=%s", assessment.get("risk_level"))

        for lang, out_dir in [("ru", ru_dir), ("kk", kk_dir), ("en", en_dir)]:
            logger.info("Формирование отчёта на %s...", lang.upper())
            report_text = get_report_in_language(assessment, lang, api_key, detected_lang)
            out_file = out_dir / "заключение.pdf"
            generate_pdf(report_text, out_file, assessment_data=assessment)
            logger.info("Сохранено: %s", out_file)

        logger.info("Готово. PDF в %s", output_dir)
        return 0

    except Exception as e:
        logger.exception("Ошибка: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
