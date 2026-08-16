"""storelib.py — store determinístico. Sem LLM. Hash = sha256 dos bytes do River."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collector_dir(store: Path, collector_id: str) -> Path:
    return store / collector_id


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


def list_collectors(store: Path):
    out = []
    if not store.is_dir():
        return out
    for meta_path in sorted(store.glob("*/meta.json")):
        meta = load_json(meta_path)
        cid = meta.get("id") or meta_path.parent.name
        river = read_river(store, cid)
        digest = sha256_bytes(river)
        if meta.get("content_hash") in (None, "", "replace-on-apply"):
            meta["content_hash"] = digest
            dump_json(meta_path, meta)
        out.append(meta)
    return out


def tokens_map(store: Path) -> dict:
    """dev_token (fixture) → collector id. Token nunca entra no River."""
    mapping = {}
    for meta in list_collectors(store):
        token = meta.get("dev_token")
        cid = meta.get("id")
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
