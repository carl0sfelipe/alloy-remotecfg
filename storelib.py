"""storelib.py — store determinístico. Sem LLM. Hash = sha256 dos bytes do River."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COLLECTOR_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_collector_id(collector_id: str) -> str:
    cid = (collector_id or "").strip()
    if not COLLECTOR_ID_RE.fullmatch(cid):
        raise ValueError(f"id inválido: {collector_id!r}")
    return cid


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, obj) -> None:
    raw = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".meta.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def collector_dir(store: Path, collector_id: str) -> Path:
    cid = require_collector_id(collector_id)
    dest = (store / cid).resolve()
    store_r = store.resolve()
    if dest != store_r and store_r not in dest.parents:
        raise ValueError(f"id fora do store: {collector_id!r}")
    return dest


def read_river(store: Path, collector_id: str) -> bytes:
    path = collector_dir(store, collector_id) / "current.alloy"
    if not path.is_file():
        raise FileNotFoundError(collector_id)
    return path.read_bytes()


def write_river(store: Path, collector_id: str, content: str) -> str:
    raw = content.encode("utf-8")
    if not raw.endswith(b"\n"):
        raw += b"\n"
    dest = collector_dir(store, collector_id) / "current.alloy"
    dest.write_bytes(raw)
    digest = sha256_bytes(raw)
    meta_path = collector_dir(store, collector_id) / "meta.json"
    meta = load_json(meta_path)
    meta["content_hash"] = digest
    dump_json(meta_path, meta)
    return digest


def list_collectors(store: Path, persist_missing_hash: bool = False):
    out = []
    if not store.is_dir():
        return out
    for meta_path in sorted(store.glob("*/meta.json")):
        meta = load_json(meta_path)
        cid = meta.get("id") or meta_path.parent.name
        try:
            require_collector_id(cid)
        except ValueError:
            continue
        river = read_river(store, cid)
        digest = sha256_bytes(river)
        if meta.get("content_hash") in (None, "", "replace-on-apply"):
            meta["content_hash"] = digest
            if persist_missing_hash:
                dump_json(meta_path, meta)
        out.append(meta)
    return out


def tokens_map(store: Path) -> dict:
    """dev_token (fixture) → collector id. Token nunca entra no River. Só lê."""
    mapping = {}
    if not store.is_dir():
        return mapping
    for meta_path in store.glob("*/meta.json"):
        try:
            meta = load_json(meta_path)
        except json.JSONDecodeError:
            continue
        token = meta.get("dev_token")
        cid = meta.get("id") or meta_path.parent.name
        try:
            require_collector_id(str(cid))
        except ValueError:
            continue
        if token and cid:
            mapping[token] = cid
    return mapping


def bearer_from_metadata(metadata) -> str:
    for key, value in metadata:
        if key.lower() == "authorization":
            raw = value.strip()
            if raw.lower().startswith("bearer "):
                return raw[7:].strip()
            return raw
    return ""
