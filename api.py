#!/usr/bin/env python3
"""REST API for AiCheck - integration with Laravel and other clients."""

import base64
import os
import tempfile
from io import BytesIO

from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.agent import analyze_tests_auto, MAX_INPUT_CHARS
from src.db import init_db, insert_check_result
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

# Optional API key (if set, clients must send X-API-Key or Authorization: Bearer <key>)
AICHECK_API_KEY = os.getenv("AICHECK_API_KEY")
MAX_UPLOAD_MB = 50


def _verify_api_key(x_api_key: str | None = None, authorization: str | None = None) -> None:
    """Raise 401 if AICHECK_API_KEY is set and request does not provide it."""
    if not AICHECK_API_KEY:
        return
    key = x_api_key
    if not key and authorization and authorization.startswith("Bearer "):
        key = authorization[7:].strip()
    if key != AICHECK_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


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


def _get_port() -> int:
    """Port for API server (AICHECK_API_PORT, or legacy PORT)."""
    return int(os.getenv("AICHECK_API_PORT", os.getenv("PORT", "41791")))


if __name__ == "__main__":
    import uvicorn
    port = _get_port()
    uvicorn.run("api:app", host="0.0.0.0", port=port)
