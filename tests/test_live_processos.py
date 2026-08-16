#!/usr/bin/env python3
"""Sobe server.py + portal.py de verdade e bate como ops faria."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv" / "bin" / "python"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_port(port: int, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"porta {port} não abriu")


class LiveProcessos(unittest.TestCase):
    def setUp(self):
        subprocess.check_call([str(PY), str(ROOT / "reset.py")], cwd=ROOT)
        self.grpc_port = _free_port()
        self.http_port = _free_port()
        env = os.environ.copy()
        self.server = subprocess.Popen(
            [str(PY), str(ROOT / "server.py"), "--port", str(self.grpc_port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.portal = subprocess.Popen(
            [str(PY), str(ROOT / "portal.py"), "--port", str(self.http_port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        _wait_port(self.grpc_port)
        _wait_port(self.http_port)

    def tearDown(self):
        for proc in (self.server, self.portal):
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        subprocess.check_call([str(PY), str(ROOT / "reset.py")], cwd=ROOT)

    def test_smoke_ok_apply_portal_rejeita(self):
        smoke = subprocess.run(
            [
                str(PY),
                str(ROOT / "smoke.py"),
                "--addr",
                f"127.0.0.1:{self.grpc_port}",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(smoke.returncode, 0, smoke.stdout + smoke.stderr)

        conn = HTTPConnection("127.0.0.1", self.http_port, timeout=3)
        body = json.dumps({"acao": "ok"}).encode()
        conn.request(
            "POST",
            "/api/decision",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        resp.read()
        resp.close()

        still = subprocess.run(
            [
                str(PY),
                str(ROOT / "smoke.py"),
                "--addr",
                f"127.0.0.1:{self.grpc_port}",
                "--id",
                "fx-02",
                "--expect-maintenance",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(still.returncode, 0, "portal ok não pode aplicar sozinho")

        applied = subprocess.run(
            [str(PY), str(ROOT / "hitl.py"), "apply", "changesets/cs-fx-maint-01.json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)

        after = subprocess.run(
            [
                str(PY),
                str(ROOT / "smoke.py"),
                "--addr",
                f"127.0.0.1:{self.grpc_port}",
                "--id",
                "fx-02",
                "--expect-maintenance",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)

        subprocess.check_call([str(PY), str(ROOT / "reset.py")], cwd=ROOT)
        rejeita = subprocess.run(
            [str(PY), str(ROOT / "hitl.py"), "rejeita", "changesets/cs-fx-maint-01.json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(rejeita.returncode, 0, rejeita.stdout + rejeita.stderr)
        no = subprocess.run(
            [
                str(PY),
                str(ROOT / "smoke.py"),
                "--addr",
                f"127.0.0.1:{self.grpc_port}",
                "--id",
                "fx-02",
                "--expect-maintenance",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(no.returncode, 0)


if __name__ == "__main__":
    unittest.main()
