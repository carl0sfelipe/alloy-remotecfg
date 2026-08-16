#!/usr/bin/env python3
"""server.py — CollectorService gRPC. GetConfig lê só current.alloy. Sem LLM."""
from __future__ import annotations

import argparse
import sys
from concurrent import futures
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "gen"))

import grpc  # noqa: E402
import collector_pb2 as pb  # noqa: E402
import collector_pb2_grpc as pb_grpc  # noqa: E402
import storelib  # noqa: E402


class CollectorService(pb_grpc.CollectorServiceServicer):
    def __init__(self, store: Path):
        self.store = store

    def _auth(self, request_id: str, context) -> str:
        try:
            cid = storelib.require_collector_id(request_id)
        except ValueError:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "id inválido")
        token = storelib.bearer_from_metadata(context.invocation_metadata())
        mapping = storelib.tokens_map(self.store)
        if not token or token not in mapping:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "bearer desconhecido")
        owner = mapping[token]
        if owner != cid:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "token não casa com id")
        return owner

    def GetConfig(self, request, context):
        cid = (request.id or "").strip()
        if not cid:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "id obrigatório")
        self._auth(cid, context)
        meta_path = storelib.collector_dir(self.store, cid) / "meta.json"
        if meta_path.is_file():
            meta = storelib.load_json(meta_path)
            if meta.get("unregistered"):
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, "collector unregistered")
        try:
            river = storelib.read_river(self.store, cid)
        except FileNotFoundError:
            context.abort(grpc.StatusCode.NOT_FOUND, cid)
        except ValueError:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "id inválido")
        digest = storelib.sha256_bytes(river)
        if request.hash and request.hash == digest:
            return pb.GetConfigResponse(content="", hash=digest, not_modified=True)
        return pb.GetConfigResponse(
            content=river.decode("utf-8"),
            hash=digest,
            not_modified=False,
        )

    def RegisterCollector(self, request, context):
        cid = (request.id or "").strip()
        if not cid:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "id obrigatório")
        self._auth(cid, context)
        meta_path = storelib.collector_dir(self.store, cid) / "meta.json"
        if not meta_path.is_file():
            context.abort(grpc.StatusCode.NOT_FOUND, cid)
        meta = storelib.load_json(meta_path)
        attrs = dict(request.local_attributes or {})
        if request.name:
            meta["name"] = request.name
        if attrs:
            meta["local_attributes"] = attrs
        storelib.dump_json(meta_path, meta)
        return pb.RegisterCollectorResponse()

    def UnregisterCollector(self, request, context):
        cid = (request.id or "").strip()
        if not cid:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "id obrigatório")
        self._auth(cid, context)
        meta_path = storelib.collector_dir(self.store, cid) / "meta.json"
        if not meta_path.is_file():
            context.abort(grpc.StatusCode.NOT_FOUND, cid)
        meta = storelib.load_json(meta_path)
        meta["unregistered"] = True
        storelib.dump_json(meta_path, meta)
        return pb.UnregisterCollectorResponse()


def serve(store: Path, bind: str, port: int) -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pb_grpc.add_CollectorServiceServicer_to_server(CollectorService(store), server)
    addr = f"{bind}:{port}"
    bound = server.add_insecure_port(addr)
    if bound == 0:
        raise SystemExit(f"porta ocupada: {addr}")
    server.start()
    print(f"GetConfig gRPC em {bind}:{bound} store={store}", flush=True)
    server.wait_for_termination()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=str(ROOT / "store"))
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9090)
    args = ap.parse_args()
    store = Path(args.store).resolve()
    if not store.is_dir():
        print(f"store ausente: {store}", file=sys.stderr)
        return 3
    storelib.list_collectors(store)
    serve(store, args.bind, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
