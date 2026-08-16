# alloy-remotecfg

> **The box keeps ~10 lines. The server holds the rest.**
> **GetConfig is code. A human still has to say ok.**

A local Grafana Alloy remote-config server. Alloy (or `smoke.py`) polls
`GetConfig`; the reply is the River already sitting in
`store/<id>/current.alloy`. A changeset becomes that file only after HITL.
No LLM on the poll path.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Proto](https://img.shields.io/badge/proto-collector.v1-orange.svg)](proto/collector.proto)

---

## Try it in 2 minutes

```bash
git clone git@github.com:carl0sfelipe/alloy-remotecfg.git
cd alloy-remotecfg

make install   # venv, official proto, two fixture collectors
make serve     # GetConfig on 127.0.0.1:9090
```

In another terminal:

```bash
make smoke     # real gRPC client; asks for fx-01 and fx-02
```

No Grafana Cloud, no card, no Alloy binary. `smoke.py` is the collector for
this proof.

---

## Why Daniel asked

**Daniel Vargas** described the shape — at Clara, where he already had the
RPC: a tiny `remotecfg {}` on each machine, a central gRPC
`CollectorService`, a portal, a fleet. Remote config plus a place for a
human to see the change and approve it. The portal was the missing piece.

This repo is that proof. Carlos built the deterministic core and put HITL
in front of apply, then a mock fleet (Mercury) in
[gigante-mocks](https://github.com/carl0sfelipe/gigante-mocks) so they could
watch 75 collectors move without touching production.

Idea: Daniel Vargas. Code here: Carlos Felipe.

---

## The loop

```
Alloy / smoke.py  --poll-->  GetConfig
                               │
                               │  Bearer authenticates
                               │  request.id selects the blob
                               │  read store/<id>/current.alloy
                               ▼
                            River + sha256
                               │
changeset  -->  HITL (ok / edit / rejeita / pula)  -->  hitl.py apply
                               │
                               ▼
                      proposed becomes current.alloy
                      next poll gets the new River
```

GetConfig never writes. `make portal` → http://127.0.0.1:8080/ records a
decision; it does not apply. Apply is `./venv/bin/python hitl.py …`.

---

## Approve one change

With `make serve` still running:

```bash
./venv/bin/python hitl.py ok changesets/cs-fx-maint-01.json
./venv/bin/python smoke.py --id fx-02 --expect-maintenance
```

`fx-02` now returns `maintenance = "true"`. Clean store: `make reset`.

Tokens `dev-fx-01` / `dev-fx-02` are fixtures, not secrets.

On the real box the local file is `collector.local.alloy` — URL, id, Bearer.
The large River never lives there.

---

## Fleet tour (Mercury)

Two fixtures are the contract. Seventy-five hosts are the show:

```bash
git clone git@github.com:carl0sfelipe/gigante-mocks.git
cd gigante-mocks
make install && make operator
```

Open **http://127.0.0.1:8088/#/tour** — Analyze → proposal → River diff →
Approve → apply. Sibling checkout expected at `~/alloy-remotecfg`
(`ALLOY_REMOTECFG_ROOT` to override).

---

## What v1 is not

- Grafana Cloud Fleet Management (SaaS; this proof is $0)
- The real Alloy binary on Connect-RPC — this slice is vanilla gRPC
  (`grpcio`). Alloy in production speaks Connect on the **same** proto;
  pin and note in `PROTO_SOURCE.txt`
- LLM-written River applied without HITL
- Ansible on 75 real machines

Proto: [grafana/alloy-remote-config](https://github.com/grafana/alloy-remote-config)
`collector.v1.CollectorService` @ `39a09f328602f1f9fabf7bb54130e76d9ecd5ce0`.
RPCs: `GetConfig`, `RegisterCollector`, `UnregisterCollector`.

---

## Layout

| Path | What |
|---|---|
| `server.py` | gRPC `CollectorService`. GetConfig reads `current.alloy` only |
| `hitl.py` | `ok` copies proposed → current; `rejeita` does not |
| `portal.py` | two machines + diff + three buttons. Decision only |
| `store/<id>/current.alloy` | the blob a collector would run |
| `changesets/*.json` | proposed River, waiting for HITL |
| `collector.local.alloy` | the ~10 lines that live on the box |
| `smoke.py` | gRPC client pretending to be Alloy |
| `proto/collector.proto` | official Grafana proto |

`make test` — unittest under `tests/`.

Apache-2.0 · **alloy-remotecfg — Carlos Felipe** · idea: Daniel Vargas
