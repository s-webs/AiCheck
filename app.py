#!/usr/bin/env python3
"""Web interface for AiCheck - upload Word file and get PDF reports."""

import os
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.agent import analyze_tests_auto, MAX_INPUT_CHARS
from src.doc_loader import load_document
from src.pdf_generator import generate_pdf
from src.translator import get_report_in_language

load_dotenv()

st.set_page_config(
    page_title="AiCheck — Проверка качества тестов",
    page_icon="📋",
    layout="centered",
)

if "results_ready" not in st.session_state:
    st.session_state.results_ready = False
    st.session_state.pdfs = {}
    st.session_state.risk_level = ""

st.title("AiCheck")
st.markdown("**Проверка качества тестовых заданий** — загрузите Word-файл (.docx) с банком тестов.")

if st.session_state.results_ready:
    st.success(f"Анализ завершён. Уровень риска: **{st.session_state.risk_level}**")
    cols = st.columns(3)
    lang_names = {"ru": "Русский", "kk": "Қазақша", "en": "English"}
    for col, (lang, pdf_bytes) in zip(cols, st.session_state.pdfs.items()):
        with col:
            st.download_button(
                f"Скачать {lang_names[lang]}",
                data=pdf_bytes,
                file_name=f"заключение_{lang}.pdf",
                mime="application/pdf",
                key=f"dl_{lang}",
            )
    if st.button("Новая проверка", type="secondary"):
        st.session_state.results_ready = False
        st.session_state.pdfs = {}
        st.session_state.risk_level = ""
        st.rerun()
    st.divider()

uploaded_file = st.file_uploader(
    "Выберите файл .docx",
    type=["docx"],
    help="Документ может быть на казахском, русском или английском языке",
)

if uploaded_file is not None and not st.session_state.results_ready:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("OPENAI_API_KEY не задан. Создайте файл .env из .env.example и укажите ключ.")
        st.stop()

    if st.button("Запустить анализ", type="primary"):
        with st.spinner("Обработка..."):
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name

            try:
                progress = st.progress(0, text="Загрузка документа...")
                file_text, detected_lang = load_document(tmp_path)
                progress.progress(20, text=f"Язык: {detected_lang}. Анализ через ИИ...")

                if not file_text.strip():
                    st.error("Документ пуст или текст не извлечён.")
                    os.unlink(tmp_path)
                    st.stop()

                if len(file_text) > MAX_INPUT_CHARS:
                    st.info(f"Документ большой ({len(file_text):,} символов). Будет чанковая обработка — все вопросы будут проверены.")

                assessment = analyze_tests_auto(file_text, detected_lang, api_key)
                progress.progress(50, text="Формирование PDF-отчётов...")

                output_dir = Path(tempfile.mkdtemp())
                ru_dir = output_dir / "ru_pdf"
                kk_dir = output_dir / "kk_pdf"
                en_dir = output_dir / "en_pdf"
                for d in (ru_dir, kk_dir, en_dir):
                    d.mkdir(parents=True, exist_ok=True)

                for lang, out_dir in [("ru", ru_dir), ("kk", kk_dir), ("en", en_dir)]:
                    report_text = get_report_in_language(assessment, lang, api_key, detected_lang)
                    out_file = out_dir / "заключение.pdf"
                    generate_pdf(report_text, out_file, assessment_data=assessment)

                progress.progress(100, text="Готово!")

                pdfs = {}
                for lang, out_dir in [("ru", ru_dir), ("kk", kk_dir), ("en", en_dir)]:
                    pdf_path = out_dir / "заключение.pdf"
                    with open(pdf_path, "rb") as f:
                        pdfs[lang] = f.read()
                st.session_state.pdfs = pdfs
                st.session_state.risk_level = assessment.get("risk_level", "N/A")
                st.session_state.results_ready = True
                st.rerun()

            except Exception as e:
                st.exception(e)
            finally:
                os.unlink(tmp_path)
