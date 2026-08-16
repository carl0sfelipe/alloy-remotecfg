#!/usr/bin/env python3
"""test_fatia1.py — GetConfig gRPC + HITL ok/rejeita. Sem LLM."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from concurrent import futures
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "gen"))

import grpc
import collector_pb2 as pb
import collector_pb2_grpc as pb_grpc
import hitl
import storelib


def _copy_fixtures(tmpdir: Path) -> Path:
    store = tmpdir / "store"
    shutil.copytree(ROOT / "fixtures" / "store", store)
    shutil.copytree(ROOT / "fixtures" / "changesets", tmpdir / "changesets")
    return store


class Fatia1(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.store = _copy_fixtures(self.td)
        from server import CollectorService

        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        pb_grpc.add_CollectorServiceServicer_to_server(
            CollectorService(self.store), self.server
        )
        self.port = self.server.add_insecure_port("127.0.0.1:0")
        self.server.start()
        self.stub = pb_grpc.CollectorServiceStub(
            grpc.insecure_channel(f"127.0.0.1:{self.port}")
        )

    def tearDown(self):
        self.server.stop(0)
        shutil.rmtree(self.td, ignore_errors=True)

    def _get(self, cid, token, hash_=""):
        return self.stub.GetConfig(
            pb.GetConfigRequest(id=cid, hash=hash_),
            metadata=(("authorization", f"Bearer {token}"),),
        )

    def test_getconfig_fx01_fx02(self):
        r1 = self._get("fx-01", "dev-fx-01")
        r2 = self._get("fx-02", "dev-fx-02")
        self.assertIn("maintenance", r1.content)
        self.assertIn('replacement  = "false"', r2.content)
        self.assertFalse(r1.not_modified)
        self.assertTrue(self._get("fx-01", "dev-fx-01", r1.hash).not_modified)

    def test_wrong_token(self):
        with self.assertRaises(grpc.RpcError) as cm:
            self._get("fx-01", "dev-fx-02")
        self.assertEqual(cm.exception.code(), grpc.StatusCode.PERMISSION_DENIED)

    def test_hitl_ok_flips_maintenance(self):
        cs = self.td / "changesets" / "cs-fx-maint-01.json"
        data = storelib.load_json(cs)
        hitl.record(data, "ok", "test")
        hitl.apply_ok(self.store, data)
        hitl.save_cs(cs, data)
        river = storelib.read_river(self.store, "fx-02").decode()
        self.assertIn('replacement  = "true"', river)
        got = self._get("fx-02", "dev-fx-02")
        self.assertIn('replacement  = "true"', got.content)
        self.assertNotEqual(got.hash, "")

    def test_hitl_rejeita_nao_copia(self):
        cs = self.td / "changesets" / "cs-fx-maint-01.json"
        data = storelib.load_json(cs)
        before = storelib.read_river(self.store, "fx-02")
        hitl.record(data, "rejeita", "test")
        hitl.save_cs(cs, data)
        self.assertEqual(storelib.read_river(self.store, "fx-02"), before)
        self.assertEqual(data["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
