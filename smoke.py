#!/usr/bin/env python3
"""smoke.py — cliente gRPC real. Prova GetConfig de fx-01 e fx-02."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "gen"))

import grpc  # noqa: E402
import collector_pb2 as pb  # noqa: E402
import collector_pb2_grpc as pb_grpc  # noqa: E402
import storelib  # noqa: E402


def stub(addr: str):
    channel = grpc.insecure_channel(addr)
    return pb_grpc.CollectorServiceStub(channel)


def metadata(token: str):
    return (("authorization", f"Bearer {token}"),)


def get_config(addr: str, collector_id: str, token: str, hash_: str = ""):
    s = stub(addr)
    return s.GetConfig(
        pb.GetConfigRequest(id=collector_id, hash=hash_),
        metadata=metadata(token),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default="127.0.0.1:9090")
    ap.add_argument("--store", default=str(ROOT / "store"))
    ap.add_argument("--id", default="")
    ap.add_argument("--expect-maintenance", action="store_true")
    args = ap.parse_args()
    store = Path(args.store)
    collectors = storelib.list_collectors(store)
    by_id = {m["id"]: m for m in collectors}
    targets = [args.id] if args.id else ["fx-01", "fx-02"]
    failed = 0
    for cid in targets:
        meta = by_id.get(cid)
        if not meta:
            print(f"FAIL {cid}: sem meta", file=sys.stderr)
            failed += 1
            continue
        token = meta["dev_token"]
        resp = get_config(args.addr, cid, token)
        river = resp.content or ""
        print(f"{cid} not_modified={resp.not_modified} hash={resp.hash[:12]}… bytes={len(river)}")
        if args.expect_maintenance:
            if 'replacement  = "true"' not in river and 'replacement = "true"' not in river:
                print(f"FAIL {cid}: maintenance true ausente no River", file=sys.stderr)
                failed += 1
            else:
                print(f"{cid} maintenance=true ok")
        elif not river.strip():
            print(f"FAIL {cid}: River vazio", file=sys.stderr)
            failed += 1
        # hash/not_modified
        again = get_config(args.addr, cid, token, hash_=resp.hash)
        if not again.not_modified:
            print(f"FAIL {cid}: hash repetido deveria not_modified", file=sys.stderr)
            failed += 1
        else:
            print(f"{cid} not_modified no 2º GetConfig ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
