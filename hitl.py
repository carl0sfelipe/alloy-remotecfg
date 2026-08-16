#!/usr/bin/env python3
"""hitl.py — ok copia proposed → current.alloy. rejeita não copia. Painel não chama isto."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import storelib

ROOT = Path(__file__).resolve().parent
ACOES = ("ok", "edit", "rejeita", "pula")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_cs(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_cs(path: Path, cs: dict) -> None:
    path.write_text(json.dumps(cs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record(cs: dict, acao: str, por: str) -> None:
    if acao not in ACOES:
        raise SystemExit(f"ação inválida: {acao}")
    cs["hitl"] = {"acao": acao, "por": por, "em": now_iso()}
    if acao == "rejeita":
        cs["status"] = "rejected"
    elif acao == "pula":
        cs["status"] = "skipped"
    elif acao == "edit":
        cs["status"] = "needs_edit"


def apply_ok(store: Path, cs: dict) -> None:
    if cs.get("status") == "approved":
        raise SystemExit("changeset já approved — make reset pra repetir")
    if cs.get("status") not in (None, "awaiting_approval", "needs_edit"):
        raise SystemExit(f"apply recusa status={cs.get('status')}")
    proposed = cs.get("proposed") or []
    if not proposed:
        raise SystemExit("changeset sem proposed")
    for item in proposed:
        cid = item["id"]
        content = item["content"]
        digest = storelib.write_river(store, cid, content)
        item["after_hash"] = digest
        meta_path = storelib.collector_dir(store, cid) / "meta.json"
        meta = storelib.load_json(meta_path)
        for op in cs.get("ops") or []:
            tags = op.get("set_tag") or {}
            meta.setdefault("tags", {}).update(tags)
        storelib.dump_json(meta_path, meta)
    cs["status"] = "approved"
    cs["hitl"]["acao"] = "ok"
    if not cs["hitl"].get("em"):
        cs["hitl"]["em"] = now_iso()
        cs["hitl"]["por"] = cs["hitl"].get("por") or "cli"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=("ok", "rejeita", "pula", "edit", "apply"))
    ap.add_argument("changeset")
    ap.add_argument("--store", default=str(ROOT / "store"))
    ap.add_argument("--por", default="cli")
    args = ap.parse_args()
    store = Path(args.store).resolve()
    path = Path(args.changeset)
    if not path.is_file():
        path = ROOT / args.changeset
    if not path.is_file():
        print(f"changeset ausente: {args.changeset}", file=sys.stderr)
        return 3
    cs = load_cs(path)
    if args.acao == "apply":
        acao = (cs.get("hitl") or {}).get("acao")
        if acao != "ok":
            print(f"apply recusa: hitl.acao={acao!r} (página grava, CLI aplica)", file=sys.stderr)
            return 1
        apply_ok(store, cs)
    elif args.acao == "ok":
        record(cs, "ok", args.por)
        apply_ok(store, cs)
    else:
        record(cs, args.acao, args.por)
    save_cs(path, cs)
    print(f"{args.acao} status={cs['status']} id={cs.get('id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
