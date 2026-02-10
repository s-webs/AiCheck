#!/usr/bin/env python3
"""AiCheck dashboard: auth, history, results, prompts, statistics, background checks."""

import base64
import os
import uuid
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from src.db import (
    create_task,
    get_check_result,
    get_stats,
    get_task,
    init_db,
    list_check_results,
    list_tasks,
    set_prompts,
    update_check_result_pdfs,
)
from src.pdf_generator import generate_pdf
from src.prompts import get_prompts
from src.translator import get_report_in_language
from src.worker import start_worker_thread

load_dotenv()
init_db()
# Start background worker once (process-level)
start_worker_thread()

st.set_page_config(
    page_title="AiCheck — Дашборд",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Session state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "view_result_id" not in st.session_state:
    st.session_state.view_result_id = None
if "results_ready" not in st.session_state:
    st.session_state.results_ready = False
if "last_result_id" not in st.session_state:
    st.session_state.last_result_id = None
if "pdfs" not in st.session_state:
    st.session_state.pdfs = {}
if "risk_level" not in st.session_state:
    st.session_state.risk_level = ""
if "last_queued_task_id" not in st.session_state:
    st.session_state.last_queued_task_id = None


def _output_root() -> Path:
    """Base directory for generated PDFs (shared with worker/CLI semantics)."""
    return Path(os.getenv("AICHECK_OUTPUT_DIR", "output"))


def check_credentials(username: str, password: str) -> bool:
    u = os.getenv("DASHBOARD_USER", "").strip()
    p = os.getenv("DASHBOARD_PASSWORD", "").strip()
    if not u or not p:
        return False
    return username == u and password == p


def login_page():
    st.title("Вход в дашборд AiCheck")
    st.markdown("Укажите логин и пароль из настроек (.env).")
    with st.form("login"):
        user = st.text_input("Логин", key="login_user")
        pwd = st.text_input("Пароль", type="password", key="login_pwd")
        submitted = st.form_submit_button("Войти")
    if submitted:
        if not user or not pwd:
            st.error("Введите логин и пароль.")
        elif not os.getenv("DASHBOARD_USER") or not os.getenv("DASHBOARD_PASSWORD"):
            st.error("DASHBOARD_USER и DASHBOARD_PASSWORD не заданы в .env. Настройте креды.")
        elif check_credentials(user, pwd):
            st.session_state.authenticated = True
            st.session_state.username = user
            st.rerun()
        else:
            st.error("Неверный логин или пароль.")


def page_new_check():
    st.subheader("Новая проверка")
    st.markdown("Загрузите файл .docx — проверка будет добавлена в очередь и выполнится в фоне. Обновите страницу «Проверки» для отслеживания.")
    uploaded_file = st.file_uploader(
        "Файл .docx",
        type=["docx"],
        help="Документ может быть на казахском, русском или английском.",
        key="upload_new",
    )
    if not uploaded_file:
        return
    if not os.getenv("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY не задан в .env.")
        return
    if st.button("Добавить в очередь", type="primary", key="run_analysis"):
        uploads_dir = Path("data/uploads")
        uploads_dir.mkdir(parents=True, exist_ok=True)
        path = uploads_dir / f"{uuid.uuid4().hex}.docx"
        path.write_bytes(uploaded_file.getvalue())
        task_id = create_task(str(path), uploaded_file.name)
        st.success(f"Проверка **#{task_id}** добавлена в очередь. Перейдите в раздел **Проверки** для отслеживания статуса.")
        st.session_state.last_queued_task_id = task_id
        st.rerun()

    if st.session_state.get("last_queued_task_id"):
        st.info(f"Последняя добавленная задача: #{st.session_state.last_queued_task_id}. Обновите страницу «Проверки».")


def page_tasks():
    st.subheader("Проверки")
    st.markdown("Список всех проверок: в очереди, в процессе, завершённые, с ошибкой. Обновите страницу для актуального статуса.")
    tasks = list_tasks(limit=100)
    if not tasks:
        st.info("Проверок пока нет. Добавьте задачу в разделе «Новая проверка».")
        return
    status_labels = {
        "pending": "В очереди",
        "in_progress": "В процессе",
        "completed": "Завершена",
        "error": "Ошибка",
    }
    for t in tasks:
        status = t.get("status") or "pending"
        label = status_labels.get(status, status)
        col1, col2, col3, col4, col5, col6 = st.columns([1, 2, 1, 1, 1, 1])
        with col1:
            st.text(f"#{t['id']}")
        with col2:
            st.text((t.get("created_at") or "")[:19] + " " + (t.get("file_name") or "—"))
        with col3:
            st.caption(label)
        with col4:
            st.text(t.get("detected_language") or "—")
        with col5:
            st.text(t.get("risk_level") or "—")
        with col6:
            if status == "completed" and t.get("result_id"):
                if st.button("Открыть", key=f"task_open_{t['id']}"):
                    st.session_state.view_result_id = t["result_id"]
                    st.rerun()
            elif status == "error" and t.get("error_message"):
                st.caption(t["error_message"][:80] + ("…" if len(t.get("error_message", "") or "") > 80 else ""))
    st.divider()


def page_history():
    st.subheader("История запросов (завершённые)")
    rows = list_check_results(limit=100)
    if not rows:
        st.info("Проверок пока нет.")
        return
    for r in rows:
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
        with col1:
            st.text(f"{r['created_at'][:19] if r.get('created_at') else '—'} {r.get('file_name') or ''}")
        with col2:
            st.text(r.get("detected_language", "—"))
        with col3:
            st.text(r.get("risk_level", "—"))
        with col4:
            st.text(str(r.get("total_tokens", 0)))
        with col5:
            if st.button("Открыть", key=f"open_{r['id']}"):
                st.session_state.view_result_id = r["id"]
                st.rerun()
    st.divider()


def page_result():
    rid = st.session_state.get("view_result_id")
    if not rid:
        st.info("Выберите запись в «История» или выполните новую проверку.")
        return
    st.subheader(f"Результат проверки #{rid}")
    row = get_check_result(rid)
    if not row:
        st.warning("Запись не найдена.")
        return
    st.caption(f"Дата: {row.get('created_at')} | Язык: {row.get('detected_language')} | Риск: {row.get('risk_level')} | Токенов: {row.get('total_tokens')}")
    assessment = row.get("assessment")
    if not assessment:
        st.write("Нет данных оценки.")
        return

    with st.expander("Общая оценка", expanded=True):
        st.write(assessment.get("overall_assessment", ""))
    st.write("**Уровень риска:**", assessment.get("risk_level", "—"))
    with st.expander("Основные выводы"):
        for f in assessment.get("major_findings", []):
            st.write(f"**[{f.get('severity')}]** {f.get('title')}")
            st.write(f.get("details", ""))
    with st.expander("Оценки качества (0–10)"):
        qs = assessment.get("quality_scores", {})
        st.json(qs)
    with st.expander("Полный JSON"):
        st.json(assessment)

    # PDF reports: allow manual generation/regen and then show available files
    st.subheader("PDF-отчёты")
    if st.button("Сгенерировать / обновить PDF-отчёты"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            st.error("OPENAI_API_KEY не задан в .env, PDF не может быть сгенерирован.")
        else:
            try:
                out_root = _output_root()
                pdf_paths: dict[str, str] = {}
                detected_lang = row.get("detected_language") or "RU"
                for lang in ("ru", "kk", "en"):
                    report_text = get_report_in_language(
                        assessment, lang, api_key, detected_lang
                    )
                    lang_dir = out_root / f"{lang}_pdf"
                    lang_dir.mkdir(parents=True, exist_ok=True)
                    out_file = lang_dir / f"conclusion_{rid}.pdf"
                    generate_pdf(report_text, out_file, assessment_data=assessment)
                    pdf_paths[lang] = str(out_file)
                update_check_result_pdfs(
                    rid,
                    pdf_ru_path=pdf_paths.get("ru"),
                    pdf_kk_path=pdf_paths.get("kk"),
                    pdf_en_path=pdf_paths.get("en"),
                )
                # Update local row so section below sees fresh paths without reload
                row["pdf_ru_path"] = pdf_paths.get("ru")
                row["pdf_kk_path"] = pdf_paths.get("kk")
                row["pdf_en_path"] = pdf_paths.get("en")
                st.success("PDF-отчёты сгенерированы.")
            except Exception as e:
                st.error(f"Ошибка при генерации PDF: {e}")

    # PDFs (if generated by background worker or via button above)
    pdf_map = {
        "RU": row.get("pdf_ru_path"),
        "KK": row.get("pdf_kk_path"),
        "EN": row.get("pdf_en_path"),
    }
    available = {k: v for k, v in pdf_map.items() if v and Path(str(v)).is_file()}
    if available:
        st.subheader("PDF-отчёты")
        cols = st.columns(3)
        for i, (lang, path) in enumerate(available.items()):
            p = Path(str(path))
            pdf_bytes = p.read_bytes()
            with cols[i % 3]:
                st.caption(f"{lang}: {p.name}")
                st.download_button(
                    label=f"Скачать {lang} PDF",
                    data=pdf_bytes,
                    file_name=p.name,
                    mime="application/pdf",
                    key=f"dl_{rid}_{lang}",
                )
                # Inline preview
                b64 = base64.b64encode(pdf_bytes).decode("utf-8")
                components.html(
                    f"""
                    <iframe
                      src="data:application/pdf;base64,{b64}"
                      width="100%"
                      height="520"
                      style="border: 1px solid #e5e7eb; border-radius: 8px;"
                    ></iframe>
                    """,
                    height=540,
                )
    else:
        st.caption("PDF для этого результата ещё не сгенерирован. Нажмите кнопку выше, чтобы сформировать отчёты.")

    if st.button("← К истории"):
        st.session_state.view_result_id = None
        st.rerun()


def page_prompts():
    st.subheader("Редактирование промптов")
    prompts = get_prompts()
    system = prompts.get("system_message") or ""
    user_tpl = prompts.get("user_message_template") or ""
    system_new = st.text_area("System message", value=system, height=200, key="prompt_system")
    user_new = st.text_area("User message template (placeholders: {detected_language}, {file_text})", value=user_tpl, height=300, key="prompt_user")
    if st.button("Сохранить промпты"):
        set_prompts(system_new, user_new)
        st.success("Промпты сохранены. Следующие проверки будут использовать новый текст.")


def page_stats():
    import pandas as pd
    st.subheader("Статистика")
    stats = get_stats()
    total_checks = stats.get("total_checks", 0)
    total_tokens = stats.get("total_tokens", 0)
    by_lang = stats.get("by_language", {})
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Всего проверок", total_checks)
    with c2:
        st.metric("Всего использовано токенов", f"{total_tokens:,}")
    if by_lang:
        st.write("**Проверок по языкам**")
        df = pd.DataFrame(list(by_lang.items()), columns=["Язык", "Количество"])
        st.bar_chart(df.set_index("Язык"))
    else:
        st.info("Нет данных по языкам.")


def main():
    if not st.session_state.authenticated:
        login_page()
        return
    st.sidebar.title("AiCheck")
    st.sidebar.caption(f"Вход: {st.session_state.username}")
    page = st.sidebar.radio(
        "Раздел",
        ["Новая проверка", "Проверки", "История", "Результат", "Промпты", "Статистика"],
        label_visibility="collapsed",
    )
    if st.sidebar.button("Выход"):
        st.session_state.authenticated = False
        st.session_state.username = ""
        st.session_state.view_result_id = None
        st.rerun()
    if page == "Новая проверка":
        page_new_check()
    elif page == "Проверки":
        page_tasks()
    elif page == "История":
        page_history()
    elif page == "Результат":
        page_result()
    elif page == "Промпты":
        page_prompts()
    else:
        page_stats()


if __name__ == "__main__":
    main()
