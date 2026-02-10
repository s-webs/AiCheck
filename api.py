#!/usr/bin/env python3
"""REST API for AiCheck - integration with Laravel and other clients."""

import base64
import os
import tempfile
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    UploadFile,
    status,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from src.agent import analyze_tests_auto, MAX_INPUT_CHARS
from src.db import (
    create_task,
    get_check_result,
    get_stats,
    get_task,
    init_db,
    insert_check_result,
    list_check_results,
    list_tasks,
    set_prompts,
    get_prompts,
    update_check_result_pdfs,
)
from src.doc_loader import load_document
from src.pdf_generator import generate_pdf
from src.translator import get_report_in_language

load_dotenv()
init_db()

app = FastAPI(
    title="AiCheck API",
    description="API for test bank quality assessment. Upload a .docx file and receive analysis plus PDF reports in RU, KK, EN.",
    version="1.0.0",
)

# CORS: allow origins from env or default to allow all for development
_cors_origins = os.getenv("CORS_ORIGINS", "*")
_origins = [o.strip() for o in _cors_origins.split(",")] if _cors_origins else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Optional API key (for external integrations like Laravel)
AICHECK_API_KEY = os.getenv("AICHECK_API_KEY")
MAX_UPLOAD_MB = 50

# Dashboard auth (JWT-based)
JWT_SECRET_KEY = os.getenv("AICHECK_JWT_SECRET", "CHANGE_ME_AICHECK_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = int(os.getenv("AICHECK_JWT_EXPIRES_MINUTES", "4320"))  # 3 days

security = HTTPBearer(auto_error=False)


def _verify_api_key(x_api_key: str | None = None, authorization: str | None = None) -> None:
    """Raise 401 if AICHECK_API_KEY is set and request does not provide it."""
    if not AICHECK_API_KEY:
        return
    key = x_api_key
    if not key and authorization and authorization.startswith("Bearer "):
        key = authorization[7:].strip()
    if key != AICHECK_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=JWT_EXPIRES_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


class UserToken(BaseModel):
    username: str


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> UserToken:
    """
    Extract and verify JWT from Authorization: Bearer <token>.
    Used to protect dashboard endpoints.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return UserToken(username=username)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _check_dashboard_credentials(username: str, password: str) -> bool:
    expected_user = os.getenv("DASHBOARD_USER", "").strip()
    expected_pass = os.getenv("DASHBOARD_PASSWORD", "").strip()
    if not expected_user or not expected_pass:
        return False
    return username == expected_user and password == expected_pass


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.post("/api/v1/auth/login", response_model=LoginResponse)
def login(data: LoginRequest, response: Response):
    """Dashboard login. Returns JWT as bearer token (can also be stored in HTTP-only cookie on client)."""
    if not _check_dashboard_credentials(data.username, data.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = _create_access_token({"sub": data.username})
    # Optional: also set HTTP-only cookie for convenience
    response.set_cookie(
        key="aicheck_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=JWT_EXPIRES_MINUTES * 60,
        path="/",
    )
    return LoginResponse(access_token=token)


@app.post("/api/v1/auth/logout")
def logout(response: Response):
    """Clear auth cookie (if used)."""
    response.delete_cookie("aicheck_token", path="/")
    return {"detail": "logged out"}


@app.get("/health")
def health():
    """Service health check for Laravel Health / monitoring."""
    return {"status": "ok"}


@app.post("/api/v1/analyze")
def analyze(
    file: UploadFile = File(..., description="Word document (.docx) with test bank"),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
):
    """
    Upload a .docx file, run AI analysis, and return assessment JSON plus PDF reports (ru, kk, en) as base64.
    Analysis may take 1–5+ minutes for large documents.
    """
    _verify_api_key(x_api_key, authorization)

    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail="Expected a .docx file. Use multipart/form-data with field 'file'.",
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY not configured. Set it in the server .env.",
        )

    content = file.file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_MB} MB.",
        )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        file_text, detected_lang = load_document(tmp_path)
        if not file_text.strip():
            raise HTTPException(
                status_code=400,
                detail="Document is empty or text could not be extracted.",
            )

        result = analyze_tests_auto(file_text, detected_lang, api_key)
        assessment = result["assessment"]
        usage = result.get("usage") or {}
        risk_level = assessment.get("risk_level", "N/A")

        pdfs_b64 = {}
        for lang in ("ru", "kk", "en"):
            report_text = get_report_in_language(
                assessment, lang, api_key, detected_lang
            )
            buffer = BytesIO()
            generate_pdf(
                report_text,
                output_path=tmp_path,  # ignored when output_stream is set
                assessment_data=assessment,
                output_stream=buffer,
            )
            pdfs_b64[lang] = base64.b64encode(buffer.getvalue()).decode("ascii")

        insert_check_result(
            detected_language=detected_lang,
            risk_level=risk_level,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            assessment=assessment,
            file_name=file.filename,
        )

        return {
            "risk_level": risk_level,
            "detected_language": detected_lang,
            "assessment": assessment,
            "pdfs": pdfs_b64,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# Convenience route without /api/v1 prefix (plan said "or without prefix")
@app.post("/analyze")
def analyze_short(
    file: UploadFile = File(..., description="Word document (.docx) with test bank"),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
):
    """Alias for POST /api/v1/analyze."""
    return analyze(file=file, x_api_key=x_api_key, authorization=authorization)


# ---------- Dashboard/SPA endpoints ----------


class TaskOut(BaseModel):
    id: int
    created_at: str
    status: str
    file_name: str | None = None
    detected_language: str | None = None
    risk_level: str | None = None
    result_id: int | None = None
    error_message: str | None = None
    total_tokens: int | None = None


class ResultSummary(BaseModel):
    id: int
    created_at: str
    detected_language: str
    risk_level: str
    total_tokens: int
    file_name: str | None = None


class ResultDetail(BaseModel):
    id: int
    created_at: str
    detected_language: str
    risk_level: str
    total_tokens: int
    file_name: str | None = None
    assessment: dict[str, Any]
    pdf_ru_path: str | None = None
    pdf_kk_path: str | None = None
    pdf_en_path: str | None = None


class StatsOut(BaseModel):
    total_checks: int
    total_tokens: int
    by_language: dict[str, int]


class PromptsOut(BaseModel):
    system_message: str
    user_message_template: str


class PromptsUpdate(BaseModel):
    system_message: str
    user_message_template: str


class PdfGenerateRequest(BaseModel):
    languages: list[str] | None = None


class PdfGenerateResponse(BaseModel):
    generated: list[str]


@app.get("/api/v1/tasks", response_model=list[TaskOut])
def list_tasks_api(current: UserToken = Depends(get_current_user)):
    rows = list_tasks(limit=200)
    return [TaskOut(**r) for r in rows]


@app.get("/api/v1/tasks/{task_id}", response_model=TaskOut)
def get_task_api(task_id: int, current: UserToken = Depends(get_current_user)):
    row = get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut(**row)


@app.post("/api/v1/tasks", response_model=TaskOut)
def create_task_api(
    file: UploadFile = File(..., description="Word document (.docx) with test bank"),
    current: UserToken = Depends(get_current_user),
):
    """Create background task by uploading a .docx file (used by dashboard/SPA)."""
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Expected a .docx file")
    uploads_dir = Path("data/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = uploads_dir / file.filename
    with tmp_path.open("wb") as f:
        f.write(file.file.read())
    task_id = create_task(str(tmp_path), file.filename)
    task = get_task(task_id)
    return TaskOut(**task)


@app.get("/api/v1/results", response_model=list[ResultSummary])
def list_results_api(current: UserToken = Depends(get_current_user)):
    rows = list_check_results(limit=200)
    out: list[ResultSummary] = []
    for r in rows:
        out.append(
            ResultSummary(
                id=r["id"],
                created_at=r["created_at"],
                detected_language=r["detected_language"],
                risk_level=r["risk_level"],
                total_tokens=r["total_tokens"],
                file_name=r.get("file_name"),
            )
        )
    return out


@app.get("/api/v1/results/{result_id}", response_model=ResultDetail)
def get_result_api(result_id: int, current: UserToken = Depends(get_current_user)):
    row = get_check_result(result_id)
    if not row:
        raise HTTPException(status_code=404, detail="Result not found")
    assessment = row.get("assessment")
    if not assessment:
        raise HTTPException(status_code=500, detail="Result has no assessment")
    return ResultDetail(
        id=row["id"],
        created_at=row["created_at"],
        detected_language=row["detected_language"],
        risk_level=row["risk_level"],
        total_tokens=row["total_tokens"],
        file_name=row.get("file_name"),
        assessment=assessment,
        pdf_ru_path=row.get("pdf_ru_path"),
        pdf_kk_path=row.get("pdf_kk_path"),
        pdf_en_path=row.get("pdf_en_path"),
    )


@app.post("/api/v1/results/{result_id}/pdf", response_model=PdfGenerateResponse)
def generate_pdfs_for_result(
    result_id: int,
    payload: PdfGenerateRequest | None = None,
    current: UserToken = Depends(get_current_user),
):
    """Generate or refresh PDFs for a stored result (used by dashboard/SPA)."""
    row = get_check_result(result_id)
    if not row:
        raise HTTPException(status_code=404, detail="Result not found")
    assessment = row.get("assessment")
    if not assessment:
        raise HTTPException(status_code=400, detail="Result has no assessment")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    detected_lang = row.get("detected_language") or "RU"
    langs = payload.languages if payload and payload.languages else ["ru", "kk", "en"]
    out_root = Path(os.getenv("AICHECK_OUTPUT_DIR", "output"))

    pdf_paths: dict[str, str] = {}
    generated: list[str] = []
    for lang in langs:
        lang_lower = lang.lower()
        if lang_lower not in ("ru", "kk", "en"):
            continue
        report_text = get_report_in_language(assessment, lang_lower, api_key, detected_lang)
        lang_dir = out_root / f"{lang_lower}_pdf"
        lang_dir.mkdir(parents=True, exist_ok=True)
        out_file = lang_dir / f"conclusion_{result_id}.pdf"
        generate_pdf(report_text, out_file, assessment_data=assessment)
        pdf_paths[lang_lower] = str(out_file)
        generated.append(lang_lower)

    if pdf_paths:
        update_check_result_pdfs(
            result_id,
            pdf_ru_path=pdf_paths.get("ru"),
            pdf_kk_path=pdf_paths.get("kk"),
            pdf_en_path=pdf_paths.get("en"),
        )

    return PdfGenerateResponse(generated=generated)


@app.get("/api/v1/results/{result_id}/pdf/{lang}")
def download_pdf_for_result(
    result_id: int,
    lang: str,
    current: UserToken = Depends(get_current_user),
):
    """Download generated PDF for a given result and language (ru/kk/en)."""
    row = get_check_result(result_id)
    if not row:
        raise HTTPException(status_code=404, detail="Result not found")
    lang_lower = lang.lower()
    if lang_lower not in ("ru", "kk", "en"):
        raise HTTPException(status_code=400, detail="Unsupported language")
    key = f"pdf_{lang_lower}_path"
    path = row.get(key)
    if not path:
        raise HTTPException(status_code=404, detail="PDF not generated")
    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found")
    filename = pdf_path.name
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=filename,
    )


@app.get("/api/v1/stats", response_model=StatsOut)
def stats_api(current: UserToken = Depends(get_current_user)):
    stats = get_stats()
    return StatsOut(
        total_checks=stats.get("total_checks", 0),
        total_tokens=stats.get("total_tokens", 0),
        by_language=stats.get("by_language", {}),
    )


@app.get("/api/v1/prompts", response_model=PromptsOut)
def get_prompts_api(current: UserToken = Depends(get_current_user)):
    p = get_prompts() or {}
    return PromptsOut(
        system_message=p.get("system_message", ""),
        user_message_template=p.get("user_message_template", ""),
    )


@app.put("/api/v1/prompts", response_model=PromptsOut)
def set_prompts_api(payload: PromptsUpdate, current: UserToken = Depends(get_current_user)):
    set_prompts(payload.system_message, payload.user_message_template)
    return PromptsOut(
        system_message=payload.system_message,
        user_message_template=payload.user_message_template,
    )


def _get_port() -> int:
    """Port for API server (AICHECK_API_PORT, or legacy PORT)."""
    return int(os.getenv("AICHECK_API_PORT", os.getenv("PORT", "41791")))


# Serve SPA build if available (mount after all API routes so /api/* works)
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa")


if __name__ == "__main__":
    import uvicorn
    port = _get_port()
    uvicorn.run("api:app", host="0.0.0.0", port=port)
