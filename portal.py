#!/usr/bin/env python3
"""portal.py — lista 2 máquinas + diff + 3 botões. Só grava decisão. Apply é hitl.py."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import storelib

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "portal.html"
DECISIONS = ROOT / "decisions.jsonl"
CHANGESET = ROOT / "changesets" / "cs-fx-maint-01.json"


def state(store: Path) -> dict:
    machines = storelib.list_collectors(store)
    cs = storelib.load_json(CHANGESET) if CHANGESET.is_file() else {}
    diffs = []
    for item in cs.get("proposed") or []:
        cid = item["id"]
        try:
            before = storelib.read_river(store, cid).decode("utf-8")
        except FileNotFoundError:
            before = ""
        diffs.append({"id": cid, "before": before, "after": item.get("content") or ""})
    return {"machines": machines, "changeset": cs, "diffs": diffs}


class Handler(BaseHTTPRequestHandler):
    store: Path = ROOT / "store"

    def _json(self, code: int, obj) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html", "/portal.html"):
            body = HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/state":
            self._json(200, state(self.store))
            return
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/decision":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", "0") or "0")
        if n <= 0 or n > 4096:
            self.send_error(400, "bad length")
            return
        try:
            body = json.loads(self.rfile.read(n))
        except json.JSONDecodeError:
            self.send_error(400, "json")
            return
        acao = str(body.get("acao") or "").strip()
        if acao not in ("ok", "edit", "rejeita"):
            self.send_error(400, "acao")
            return
        if not CHANGESET.is_file():
            self.send_error(404, "changeset")
            return
        cs = storelib.load_json(CHANGESET)
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        cs["hitl"] = {"acao": acao, "por": "portal", "em": now}
        storelib.dump_json(CHANGESET, cs)
        entry = {"ts": now, "acao": acao, "changeset": cs.get("id"), "applied": False}
        with DECISIONS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._json(200, {"ok": True, "acao": acao, "apply": "python3 hitl.py apply changesets/cs-fx-maint-01.json"})

    def log_message(self, fmt, *args):
        sys.stderr.write("[portal] " + (fmt % args) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=str(ROOT / "store"))
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    Handler.store = Path(args.store).resolve()
    httpd = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"portal http://{args.bind}:{args.port}/  (só grava decisão; apply = hitl.py)", flush=True)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
