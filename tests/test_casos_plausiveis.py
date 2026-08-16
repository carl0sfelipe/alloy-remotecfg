#!/usr/bin/env python3
"""Casos plausíveis de frota: token, isolamento, lote 15, portal, register.

Não fala com Grafana Cloud. Sem LLM no caminho do GetConfig.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
from concurrent import futures
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "gen"))

import grpc
import collector_pb2 as pb
import collector_pb2_grpc as pb_grpc
import hitl
import portal
import storelib
from server import CollectorService

RIVER_OFF = """logging {
  level = "info"
}

prometheus.relabel "host_tags" {
  rule {
    target_label = "role"
    replacement  = "web"
  }
  rule {
    target_label = "maintenance"
    replacement  = "false"
  }
}
"""

RIVER_ON = RIVER_OFF.replace('replacement  = "false"', 'replacement  = "true"', 1)


def _write_collector(store: Path, cid: str, token: str, river: str = RIVER_OFF) -> None:
    d = store / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "current.alloy").write_text(river, encoding="utf-8")
    digest = storelib.sha256_bytes(river.encode("utf-8"))
    storelib.dump_json(
        d / "meta.json",
        {
            "id": cid,
            "name": cid,
            "tags": {"role": "web", "maintenance": "false"},
            "content_hash": digest,
            "dev_token": token,
        },
    )


def _copy_fixtures(tmpdir: Path) -> Path:
    store = tmpdir / "store"
    shutil.copytree(ROOT / "fixtures" / "store", store)
    shutil.copytree(ROOT / "fixtures" / "changesets", tmpdir / "changesets")
    return store


class GrpcCasos(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.store = _copy_fixtures(self.td)
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        pb_grpc.add_CollectorServiceServicer_to_server(
            CollectorService(self.store), self.server
        )
        self.port = self.server.add_insecure_port("127.0.0.1:0")
        self.server.start()
        self.channel = grpc.insecure_channel(f"127.0.0.1:{self.port}")
        self.stub = pb_grpc.CollectorServiceStub(self.channel)

    def tearDown(self):
        self.channel.close()
        self.server.stop(0)
        shutil.rmtree(self.td, ignore_errors=True)

    def _get(self, cid, token, hash_="", **kwargs):
        md = kwargs.pop("metadata", (("authorization", f"Bearer {token}"),))
        return self.stub.GetConfig(
            pb.GetConfigRequest(id=cid, hash=hash_, **kwargs),
            metadata=md,
        )

    def test_maquina_pergunta_caderno_certo(self):
        r = self._get("fx-01", "dev-fx-01")
        self.assertIn("fx-01", storelib.tokens_map(self.store)["dev-fx-01"])
        self.assertIn("maintenance", r.content)
        self.assertNotIn("dev-fx-01", r.content)
        self.assertNotIn("Bearer", r.content)

    def test_token_da_outra_maquina(self):
        with self.assertRaises(grpc.RpcError) as cm:
            self._get("fx-01", "dev-fx-02")
        self.assertEqual(cm.exception.code(), grpc.StatusCode.PERMISSION_DENIED)

    def test_token_inventado(self):
        with self.assertRaises(grpc.RpcError) as cm:
            self._get("fx-01", "totally-fake")
        self.assertEqual(cm.exception.code(), grpc.StatusCode.UNAUTHENTICATED)

    def test_sem_authorization(self):
        with self.assertRaises(grpc.RpcError) as cm:
            self.stub.GetConfig(pb.GetConfigRequest(id="fx-01"), metadata=())
        self.assertEqual(cm.exception.code(), grpc.StatusCode.UNAUTHENTICATED)

    def test_id_vazio(self):
        with self.assertRaises(grpc.RpcError) as cm:
            self._get("", "dev-fx-01")
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_maquina_inexistente_token_bate(self):
        # token de fx-01 contra id que não existe → permission (token não casa)
        with self.assertRaises(grpc.RpcError) as cm:
            self._get("ghost-99", "dev-fx-01")
        self.assertEqual(cm.exception.code(), grpc.StatusCode.PERMISSION_DENIED)

    def test_poll_igual_nao_manda_caderno_de_novo(self):
        first = self._get("fx-02", "dev-fx-02")
        second = self._get("fx-02", "dev-fx-02", first.hash)
        self.assertTrue(second.not_modified)
        self.assertEqual(second.content, "")
        self.assertEqual(second.hash, first.hash)

    def test_hash_velho_depois_da_manutencao_puxa_caderno_novo(self):
        before = self._get("fx-02", "dev-fx-02")
        cs = storelib.load_json(self.td / "changesets" / "cs-fx-maint-01.json")
        hitl.record(cs, "ok", "ops")
        hitl.apply_ok(self.store, cs)
        after = self._get("fx-02", "dev-fx-02", before.hash)
        self.assertFalse(after.not_modified)
        self.assertIn('replacement  = "true"', after.content)
        self.assertNotEqual(after.hash, before.hash)

    def test_ok_nao_mexe_na_irma(self):
        cs = storelib.load_json(self.td / "changesets" / "cs-fx-maint-01.json")
        river_01 = storelib.read_river(self.store, "fx-01")
        hitl.record(cs, "ok", "ops")
        hitl.apply_ok(self.store, cs)
        self.assertEqual(storelib.read_river(self.store, "fx-01"), river_01)
        self.assertIn('replacement  = "false"', self._get("fx-01", "dev-fx-01").content)

    def test_rejeita_nao_aplica(self):
        before = storelib.read_river(self.store, "fx-02")
        cs_path = self.td / "changesets" / "cs-fx-maint-01.json"
        cs = storelib.load_json(cs_path)
        hitl.record(cs, "rejeita", "ops")
        hitl.save_cs(cs_path, cs)
        self.assertEqual(storelib.read_river(self.store, "fx-02"), before)
        got = self._get("fx-02", "dev-fx-02")
        self.assertIn('replacement  = "false"', got.content)

    def test_pula_e_edit_nao_copiam(self):
        before = storelib.read_river(self.store, "fx-02")
        for acao in ("pula", "edit"):
            cs = storelib.load_json(self.td / "changesets" / "cs-fx-maint-01.json")
            hitl.record(cs, acao, "ops")
            self.assertEqual(storelib.read_river(self.store, "fx-02"), before)

    def test_double_ok_recusa(self):
        cs = storelib.load_json(self.td / "changesets" / "cs-fx-maint-01.json")
        hitl.record(cs, "ok", "ops")
        hitl.apply_ok(self.store, cs)
        with self.assertRaises(SystemExit):
            hitl.apply_ok(self.store, cs)

    def test_apply_cli_sem_ok_do_portal_recusa(self):
        cs = storelib.load_json(self.td / "changesets" / "cs-fx-maint-01.json")
        acao = (cs.get("hitl") or {}).get("acao")
        self.assertNotEqual(acao, "ok")
        before = storelib.read_river(self.store, "fx-02")
        self.assertEqual(storelib.read_river(self.store, "fx-02"), before)

    def test_register_grava_hostname_sem_mudar_river(self):
        river = storelib.read_river(self.store, "fx-01")
        self.stub.RegisterCollector(
            pb.RegisterCollectorRequest(
                id="fx-01",
                name="web-01.prod",
                local_attributes={"hostname": "web-01", "cluster": "prod"},
            ),
            metadata=(("authorization", "Bearer dev-fx-01"),),
        )
        self.assertEqual(storelib.read_river(self.store, "fx-01"), river)
        meta = storelib.load_json(self.store / "fx-01" / "meta.json")
        self.assertEqual(meta["name"], "web-01.prod")
        self.assertEqual(meta["local_attributes"]["hostname"], "web-01")

    def test_unregister_corta_o_caderno(self):
        self.stub.UnregisterCollector(
            pb.UnregisterCollectorRequest(id="fx-02"),
            metadata=(("authorization", "Bearer dev-fx-02"),),
        )
        meta = storelib.load_json(self.store / "fx-02" / "meta.json")
        self.assertTrue(meta.get("unregistered"))
        with self.assertRaises(grpc.RpcError) as cm:
            self._get("fx-02", "dev-fx-02")
        self.assertEqual(cm.exception.code(), grpc.StatusCode.FAILED_PRECONDITION)

    def test_attributes_nao_escolhem_o_blob(self):
        # GetConfig ignora local_attributes na fatia 1 — id manda
        r = self._get(
            "fx-01",
            "dev-fx-01",
            local_attributes={"role": "db", "maintenance": "true"},
        )
        self.assertIn('replacement  = "false"', r.content)
        self.assertIn('replacement  = "web"', r.content)

    def test_path_traversal_id_nao_le_outra_pasta(self):
        with self.assertRaises(grpc.RpcError) as cm:
            self._get("../fx-01", "dev-fx-01")
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)
        with self.assertRaises(grpc.RpcError) as cm:
            self._get("fx-01/../fx-02", "dev-fx-01")
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)

    def test_poll_concorrente_20_vezes(self):
        errors = []

        def once():
            try:
                r = self._get("fx-01", "dev-fx-01")
                if "maintenance" not in r.content:
                    errors.append("caderno vazio")
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))

        threads = [threading.Thread(target=once) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


class LoteQuinze(unittest.TestCase):
    """15 web em manutenção, 3 de fora intactas — o caso do amigo em miniatura."""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.store = self.td / "store"
        self.store.mkdir()
        for i in range(1, 19):
            cid = f"web-{i:02d}"
            _write_collector(self.store, cid, f"tok-{cid}")
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        pb_grpc.add_CollectorServiceServicer_to_server(
            CollectorService(self.store), self.server
        )
        self.port = self.server.add_insecure_port("127.0.0.1:0")
        self.server.start()
        self.channel = grpc.insecure_channel(f"127.0.0.1:{self.port}")
        self.stub = pb_grpc.CollectorServiceStub(self.channel)

    def tearDown(self):
        self.channel.close()
        self.server.stop(0)
        shutil.rmtree(self.td, ignore_errors=True)

    def test_quinze_em_manutencao_tres_ficam(self):
        alvos = [f"web-{i:02d}" for i in range(1, 16)]
        de_fora = [f"web-{i:02d}" for i in range(16, 19)]
        cs = {
            "id": "cs-maint-15",
            "status": "awaiting_approval",
            "ops": [{"set_tag": {"maintenance": "true"}}],
            "proposed": [
                {"id": cid, "content": RIVER_ON} for cid in alvos
            ],
            "hitl": {"acao": None, "por": None, "em": None},
        }
        hitl.record(cs, "ok", "ops")
        hitl.apply_ok(self.store, cs)
        for cid in alvos:
            got = self.stub.GetConfig(
                pb.GetConfigRequest(id=cid),
                metadata=(("authorization", f"Bearer tok-{cid}"),),
            )
            self.assertIn('replacement  = "true"', got.content, cid)
            meta = storelib.load_json(self.store / cid / "meta.json")
            self.assertEqual(meta["tags"]["maintenance"], "true", cid)
        for cid in de_fora:
            got = self.stub.GetConfig(
                pb.GetConfigRequest(id=cid),
                metadata=(("authorization", f"Bearer tok-{cid}"),),
            )
            self.assertIn('replacement  = "false"', got.content, cid)
            meta = storelib.load_json(self.store / cid / "meta.json")
            self.assertEqual(meta["tags"]["maintenance"], "false", cid)


class PortalNaoAplica(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.store = _copy_fixtures(self.td)
        self.cs = self.td / "changesets" / "cs-fx-maint-01.json"
        self.decisions = self.td / "decisions.jsonl"
        self._orig = (portal.CHANGESET, portal.DECISIONS)
        portal.CHANGESET = self.cs
        portal.DECISIONS = self.decisions
        portal.Handler.store = self.store
        self.httpd = portal.ThreadingHTTPServer(("127.0.0.1", 0), portal.Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        portal.CHANGESET, portal.DECISIONS = self._orig
        shutil.rmtree(self.td, ignore_errors=True)

    def _post(self, acao: str, extra=None):
        body = json.dumps({"acao": acao, **(extra or {})}).encode()
        conn = HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request(
            "POST",
            "/api/decision",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        return conn.getresponse()

    def test_botao_ok_nao_muda_river(self):
        before = storelib.read_river(self.store, "fx-02")
        resp = self._post("ok")
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read())
        resp.close()
        self.assertTrue(payload["ok"])
        self.assertIn("hitl.py apply", payload["apply"])
        self.assertEqual(storelib.read_river(self.store, "fx-02"), before)
        cs = storelib.load_json(self.cs)
        self.assertEqual(cs["hitl"]["acao"], "ok")
        self.assertNotEqual(cs.get("status"), "approved")
        lines = self.decisions.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(json.loads(lines[-1])["applied"], False)

    def test_portal_ok_depois_cli_apply(self):
        resp = self._post("ok")
        self.assertEqual(resp.status, 200)
        resp.read()
        resp.close()
        cs = storelib.load_json(self.cs)
        self.assertEqual(cs["hitl"]["acao"], "ok")
        hitl.apply_ok(self.store, cs)
        hitl.save_cs(self.cs, cs)
        river = storelib.read_river(self.store, "fx-02").decode()
        self.assertIn('replacement  = "true"', river)

    def test_portal_rejeita_apply_recusa(self):
        resp = self._post("rejeita")
        self.assertEqual(resp.status, 200)
        resp.read()
        resp.close()
        before = storelib.read_river(self.store, "fx-02")
        cs = storelib.load_json(self.cs)
        self.assertEqual((cs.get("hitl") or {}).get("acao"), "rejeita")
        self.assertEqual(storelib.read_river(self.store, "fx-02"), before)

    def test_acao_lixo_400(self):
        resp = self._post("explode")
        self.assertEqual(resp.status, 400)
        resp.read()
        resp.close()

    def test_state_lista_duas_maquinas(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request("GET", "/api/state")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read())
        resp.close()
        ids = {m["id"] for m in data["machines"]}
        self.assertEqual(ids, {"fx-01", "fx-02"})
        self.assertEqual(len(data["diffs"]), 1)


if __name__ == "__main__":
    unittest.main()
