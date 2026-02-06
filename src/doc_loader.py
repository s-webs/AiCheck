"""Extract text from Word documents and detect language."""

import re
from pathlib import Path
from docx import Document


def extract_text_from_docx(path: str | Path) -> str:
    """
    Extract all text from a .docx file, preserving order.
    Includes paragraphs and table cells.
    """
    path = Path(path)
    if not path.suffix.lower() == ".docx":
        raise ValueError(f"Expected .docx file, got {path.suffix}")

    doc = Document(path)
    parts: list[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            parts.append(text)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text:
                    parts.append(text)

    return "\n\n".join(parts)


def detect_language(text: str) -> str:
    """
    Detect language using Unicode character heuristics.
    Returns: "RU" | "KK" | "EN"
    """
    if not text or not text.strip():
        return "RU"

    sample = text[:3000]
    cyrillic_count = 0
    latin_count = 0
    kk_specific = 0  # ғ, қ, ң, ө, ү, һ, і

    kk_chars = "ғқңөүһі"
    for char in sample:
        if "\u0400" <= char <= "\u04FF":  # Cyrillic
            cyrillic_count += 1
            if char.lower() in kk_chars:
                kk_specific += 1
        elif "a" <= char.lower() <= "z":
            latin_count += 1

    if cyrillic_count > latin_count:
        if kk_specific >= 3:
            return "KK"
        return "RU"
    return "EN"


def load_document(path: str | Path) -> tuple[str, str]:
    """
    Load a Word document and return (text, detected_language).
    """
    text = extract_text_from_docx(path)
    lang = detect_language(text)
    return text, lang


def split_into_question_chunks(text: str, max_chars_per_chunk: int) -> list[tuple[str, int]]:
    """
    Split text into chunks by question boundaries.
    Each chunk stays under max_chars_per_chunk, aligned to question boundaries.
    Returns list of (chunk_text, question_offset) where offset is the starting question number.

    Question boundaries: lines starting with "1.", "2)", "Вопрос №5", "Question 1", etc.
    """
    if not text.strip():
        return []

    # Split by double newlines followed by question-like start
    # Patterns: "1.", "1)", "Вопрос №1", "Question 1", "1. "
    question_start = re.compile(
        r'\n\s*\n(?=(?:\d+[\.\)]\s|\d+\.\s|Вопрос\s*№?\s*\d+|Question\s+\d+|\d+\.\s))',
        re.IGNORECASE
    )
    parts = question_start.split(text)

    # Filter empty and build chunks
    blocks = [p.strip() for p in parts if p.strip()]

    if not blocks:
        # Fallback: split by fixed size at newline boundaries
        chunks = []
        remaining = text
        offset = 1  # 1-based first question in chunk
        while remaining:
            if len(remaining) <= max_chars_per_chunk:
                chunks.append((remaining, offset))
                break
            cut = remaining[:max_chars_per_chunk]
            last_newline = cut.rfind('\n')
            if last_newline > max_chars_per_chunk // 2:
                cut = cut[:last_newline + 1]
            chunks.append((cut, offset))
            remaining = remaining[len(cut):].lstrip()
            # Rough estimate: ~500 chars per question
            offset += max(1, len(cut) // 500)
        return chunks

    chunks: list[tuple[str, int]] = []
    current: list[str] = []
    current_len = 0
    next_question_offset = 1  # 1-based index of first question in next chunk

    for block in blocks:
        block_len = len(block) + 2  # +2 for "\n\n"
        if block_len > max_chars_per_chunk:
            # Single block too large: split by size at newline boundaries
            remaining = block
            while remaining:
                if len(remaining) <= max_chars_per_chunk:
                    current.append(remaining)
                    current_len += len(remaining) + 2
                    break
                cut = remaining[:max_chars_per_chunk]
                last_nl = cut.rfind('\n')
                if last_nl > max_chars_per_chunk // 2:
                    cut = cut[:last_nl + 1]
                current.append(cut)
                current_len += len(cut) + 2
                if current_len > max_chars_per_chunk:
                    chunk_text = "\n\n".join(current)
                    chunks.append((chunk_text, next_question_offset))
                    next_question_offset += len(current)
                    current = []
                    current_len = 0
                remaining = remaining[len(cut):].lstrip()
            continue
        if current_len + block_len > max_chars_per_chunk and current:
            chunk_text = "\n\n".join(current)
            chunks.append((chunk_text, next_question_offset))
            next_question_offset += len(current)
            current = []
            current_len = 0
        current.append(block)
        current_len += block_len

    if current:
        chunk_text = "\n\n".join(current)
        chunks.append((chunk_text, next_question_offset))

    return chunks
