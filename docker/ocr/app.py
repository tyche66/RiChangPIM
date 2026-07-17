import asyncio
import hashlib
import io
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pypdf import PdfReader

app = FastAPI(title="AI-PIM Local OCR")

MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_PAGES = 50


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "engine": "tesseract", "version": _version()}


def _version() -> str:
    result = subprocess.run(
        ["tesseract", "--version"], capture_output=True, text=True, check=True, timeout=5
    )
    return result.stdout.splitlines()[0].replace("tesseract ", "")


def _ocr_pdf(content: bytes) -> dict:
    try:
        page_count = len(PdfReader(io.BytesIO(content)).pages)
    except Exception as exc:
        raise ValueError("invalid_pdf") from exc
    if page_count == 0:
        raise ValueError("empty_pdf")
    if page_count > MAX_PAGES:
        raise ValueError(f"page_limit_exceeded:{page_count}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.pdf"
        source.write_bytes(content)
        subprocess.run(
            ["pdftoppm", "-png", "-r", "200", str(source), str(root / "page")],
            check=True,
            capture_output=True,
            timeout=120,
        )
        texts = []
        for image in sorted(root.glob("page-*.png")):
            result = subprocess.run(
                ["tesseract", str(image), "stdout", "-l", "chi_sim+eng"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.stdout.strip():
                texts.append(result.stdout.strip())

    text = "\n\n".join(texts).strip()
    if not text:
        raise ValueError("empty_ocr_result")
    return {
        "text": text,
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "page_count": page_count,
        "engine": "tesseract",
        "version": _version(),
    }


@app.post("/ocr/pdf")
async def ocr_pdf(file: UploadFile = File(...)) -> dict:
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="file_too_large")
    try:
        return await asyncio.wait_for(asyncio.to_thread(_ocr_pdf, content), timeout=300)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="ocr_timeout") from exc
    except (ValueError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
