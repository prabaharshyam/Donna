"""Document drop: store files, extract text, chunk + index for retrieval, detect key dates."""
import base64
import json
import logging
import re
import secrets
import threading
import zipfile
from pathlib import Path

from . import db, llm

log = logging.getLogger("donna.docs")
DOC_DIR = db.DATA_DIR / "docs"
DOC_DIR.mkdir(exist_ok=True)
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".log", ".html", ".htm", ".eml"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED = TEXT_EXT | IMG_EXT | {".pdf", ".docx"}
MAX_BYTES = 25 * 1024 * 1024


def save_upload(filename: str, data: bytes, mime: str = ""):
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise ValueError(f"Unsupported file type {ext}. Use PDF, Word (.docx), text or an image.")
    if len(data) > MAX_BYTES:
        raise ValueError("File is larger than 25 MB")
    stored = secrets.token_hex(12) + ext
    (DOC_DIR / stored).write_bytes(data)
    title = Path(filename).stem.replace("_", " ").replace("-", " ").strip() or filename
    did = db.run("INSERT INTO documents(title, filename, stored_name, mime, size) VALUES (?,?,?,?,?)",
                 (title, filename, stored, mime, len(data)))
    threading.Thread(target=process, args=(did,), daemon=True).start()
    return db.row("SELECT * FROM documents WHERE id=?", (did,))


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        r = PdfReader(str(path))
        return "\n\n".join((p.extract_text() or "") for p in r.pages[:200])
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf8", "ignore")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml)
    if ext in IMG_EXT:
        b64 = base64.b64encode(path.read_bytes()).decode()
        return llm.complete([{"role": "user", "images": [b64], "content":
                              "Transcribe ALL text in this image exactly, then list any key details (names, numbers, dates, amounts). Plain text only."}],
                            timeout=300)
    raw = path.read_text(errors="ignore")
    if ext in (".html", ".htm"):
        raw = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", raw)
        raw = re.sub(r"<[^>]+>", " ", raw)
    return raw


def chunk(text: str, size=900, overlap=150):
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    out, i = [], 0
    while i < len(text):
        end = min(len(text), i + size)
        if end < len(text):
            cut = max(text.rfind("\n", i + size // 2, end), text.rfind(". ", i + size // 2, end))
            if cut > i:
                end = cut + 1
        out.append(text[i:end].strip())
        if end >= len(text):
            break
        i = max(end - overlap, i + 1)
    return [c for c in out if c]


def process(did: int):
    d = db.row("SELECT * FROM documents WHERE id=?", (did,))
    try:
        text = extract_text(DOC_DIR / d["stored_name"])
        if not text.strip():
            raise ValueError("No readable text found (scanned PDF? Try uploading a photo of it instead)")
        db.run("DELETE FROM doc_chunks WHERE doc_id=?", (did,))
        for i, c in enumerate(chunk(text)):
            cid = db.run("INSERT INTO doc_chunks(doc_id, idx, text) VALUES (?,?,?)", (did, i, c))
            db.index("doc", cid, d["title"], c)
        db.run("UPDATE documents SET status='indexed' WHERE id=?", (did,))
        analyse(did, text)
        db.run("UPDATE documents SET status='ready' WHERE id=?", (did,))
    except Exception as e:
        log.exception("document %s failed", did)
        db.run("UPDATE documents SET status='error', error=? WHERE id=?", (str(e)[:300], did))


def analyse(did, text):
    from .agents import skill
    schema = {"type": "object", "properties": {
        "title": {"type": "string"}, "summary": {"type": "string"},
        "dates": {"type": "array", "items": {"type": "object", "properties": {
            "label": {"type": "string"}, "date": {"type": "string"}}, "required": ["label", "date"]}}},
        "required": ["title", "summary", "dates"]}
    try:
        out = json.loads(llm.complete([{"role": "system", "content": skill("documents")},
                                       {"role": "user", "content": text[:6000]}], fmt=schema, timeout=240))
    except Exception as e:
        log.warning("analyse failed: %s", e)
        return
    dates = [x for x in out.get("dates", []) if re.match(r"^\d{4}-\d{2}-\d{2}$", x.get("date", ""))][:8]
    title = (out.get("title") or "").strip()[:80]
    sets = "summary=?, dates=?" + (", title=?" if title else "")
    args = [out.get("summary", "")[:800], json.dumps(dates)] + ([title] if title else []) + [did]
    db.run(f"UPDATE documents SET {sets} WHERE id=?", args)
    if title:
        for c in db.rows("SELECT id, text FROM doc_chunks WHERE doc_id=?", (did,)):
            db.index("doc", c["id"], title, c["text"])


def documents():
    out = db.rows("SELECT d.*, (SELECT COUNT(*) FROM doc_chunks c WHERE c.doc_id=d.id) AS chunks FROM documents d ORDER BY id DESC")
    for d in out:
        d["dates"] = json.loads(d["dates"] or "[]")
    return out


def delete(did):
    d = db.row("SELECT * FROM documents WHERE id=?", (did,))
    if not d:
        return
    for c in db.rows("SELECT id FROM doc_chunks WHERE doc_id=?", (did,)):
        db.unindex("doc", c["id"])
    db.run("DELETE FROM documents WHERE id=?", (did,))
    (DOC_DIR / d["stored_name"]).unlink(missing_ok=True)


def search(query, limit=5):
    out = []
    for h in db.search(query, ["doc"], limit):
        c = db.row("SELECT c.text, d.title, d.id AS doc_id FROM doc_chunks c JOIN documents d ON d.id=c.doc_id WHERE c.id=?", (h["ref_id"],))
        if c:
            out.append({"document": c["title"], "doc_id": c["doc_id"], "excerpt": c["text"][:900]})
    return out
