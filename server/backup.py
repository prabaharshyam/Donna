"""Full backup / restore of everything in the data folder: database, app key and documents.

Used to move Donna between machines (e.g. this Mac → a cloud server). A restore is staged as
data/restore-pending.zip and applied at the next start, before the database is opened.
"""
import io
import logging
import os
import shutil
import sqlite3
import threading
import time
import zipfile
from pathlib import PurePosixPath

from . import db

log = logging.getLogger("donna.backup")
PENDING = "restore-pending.zip"
MAX_RESTORE_BYTES = 500 * 1024 * 1024


def build_zip() -> bytes:
    """Consistent snapshot: the SQLite online-backup API copies the live database safely."""
    buf = io.BytesIO()
    snap = db.DATA_DIR / ".backup-snapshot.db"
    src = sqlite3.connect(db.DB_PATH)
    dst = sqlite3.connect(snap)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(snap, "donna.db")
        key = db.DATA_DIR / ".appkey"
        if key.exists():
            z.write(key, ".appkey")
        docs = db.DATA_DIR / "docs"
        if docs.exists():
            for f in sorted(docs.iterdir()):
                if f.is_file():
                    z.write(f, f"docs/{f.name}")
        z.writestr("DONNA_BACKUP", f"created {db.now()}\n")
    snap.unlink(missing_ok=True)
    return buf.getvalue()


def _safe_members(z: zipfile.ZipFile):
    """Only the files a Donna backup contains; rejects path traversal and anything else."""
    names = z.namelist()
    if "donna.db" not in names or "DONNA_BACKUP" not in names:
        raise ValueError("This isn't a Donna backup (missing donna.db)")
    ok = []
    for n in names:
        p = PurePosixPath(n)
        if n in ("donna.db", ".appkey", "DONNA_BACKUP"):
            ok.append(n)
        elif len(p.parts) == 2 and p.parts[0] == "docs" and not p.name.startswith(".") and ".." not in n:
            ok.append(n)
    return ok


def stage_restore(data: bytes):
    if len(data) > MAX_RESTORE_BYTES:
        raise ValueError("Backup is larger than 500 MB")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        _safe_members(z)
        with z.open("donna.db") as f:
            if f.read(16) != b"SQLite format 3\x00":
                raise ValueError("The backup's database is not a valid SQLite file")
    (db.DATA_DIR / PENDING).write_bytes(data)


def restart_soon(delay=1.5):
    """Exit so the host (Docker/Railway/Fly) restarts Donna, which then applies the staged restore."""
    def _go():
        time.sleep(delay)
        log.warning("Restarting to apply restored backup")
        os._exit(3)
    threading.Thread(target=_go, daemon=True).start()


def apply_pending_restore():
    pending = db.DATA_DIR / PENDING
    if not pending.exists():
        return False
    try:
        with zipfile.ZipFile(pending) as z:
            members = _safe_members(z)
            # keep the current state aside in case something goes wrong
            keep = db.DATA_DIR / f"pre-restore-{time.strftime('%Y%m%d-%H%M%S')}"
            keep.mkdir()
            for name in ("donna.db", ".appkey"):
                if (db.DATA_DIR / name).exists():
                    shutil.copy2(db.DATA_DIR / name, keep / name)
            for suffix in ("-wal", "-shm"):
                (db.DATA_DIR / f"donna.db{suffix}").unlink(missing_ok=True)
            (db.DATA_DIR / "docs").mkdir(exist_ok=True)
            for n in members:
                if n == "DONNA_BACKUP":
                    continue
                target = db.DATA_DIR / n
                with z.open(n) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                if n == ".appkey":
                    os.chmod(target, 0o600)
        log.warning("Backup restored (previous files kept in %s)", keep.name)
        return True
    finally:
        pending.unlink(missing_ok=True)
