"""
post2/db.py — Thread-safe JSON database for caching Cloudflare session data.

Stores:  { "https://teraboxdl.site/": { "headers": {"User-Agent": "...", ...}, "cookies": [...], "cached_at": 1234 } }
File lives at /config/post2_db.json inside the container (or a path set by POST2_DB_PATH env var).
"""
import json
import logging
import os
import threading
import time

# Allow overriding the path via env var so it can be mounted as a volume
# Default to /config which is the writable Docker volume mount point
DEFAULT_DB_PATH = "/config/post2_db.json"
DB_PATH = os.environ.get("POST2_DB_PATH", DEFAULT_DB_PATH)

_lock = threading.Lock()


def _load() -> dict:
    """Load the raw JSON db from disk. Returns empty dict on missing/corrupt file."""
    try:
        with open(DB_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(db: dict) -> None:
    """Persist the db dict to disk atomically."""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(db, f, indent=2)
    os.replace(tmp, DB_PATH)


def get(base_url: str) -> dict | None:
    """Return cached session data for base_url, or None if not present."""
    with _lock:
        db = _load()
        return db.get(base_url)


def put(base_url: str, cookies: list, headers: dict) -> None:
    """Store/overwrite session data for base_url.

    Saves cookies (including cf_clearance) and headers (including User-Agent).
    cf_clearance is already inside the cookies list
    as a dict with {"name": "cf_clearance", "value": "..."}.
    """
    with _lock:
        db = _load()
        db[base_url] = {
            "cookies": cookies,
            "headers": headers,
            "cached_at": int(time.time()),
        }
        _save(db)
    logging.info(f"[post2/db] Cached session for {base_url}")


def remove(base_url: str) -> None:
    """Delete cached session for base_url (called on 403 before retry)."""
    with _lock:
        db = _load()
        if base_url in db:
            del db[base_url]
            _save(db)
    logging.info(f"[post2/db] Evicted session for {base_url}")
