cd /Users/mini/alloy-remotecfg && make install && make serve

Fatia 1 — GetConfig gRPC burro + HITL apply + uma página. Sem IA no caminho do Alloy.

## 3 comandos

1. `make install` — venv, proto, fixtures
2. `make serve` — gRPC em `127.0.0.1:9090`
3. Noutro terminal: `make smoke`

HITL (depois do serve): `./venv/bin/python hitl.py ok changesets/cs-fx-maint-01.json` e de novo `make smoke` com `./venv/bin/python smoke.py --id fx-02 --expect-maintenance`

Página (opcional): `make portal` → http://127.0.0.1:8080/ — botão só grava decisão; apply continua `hitl.py apply`.

Repetir: `make reset`

## O que é isto

Repo irmão do oracfit (regra 52). Contrato/ponteiro: `/Users/mini/oracfit/docs/architecture/alloy-remotecfg/`. Proto oficial `grafana/alloy-remote-config` @ `39a09f328602f1f9fabf7bb54130e76d9ecd5ce0`. Tokens `dev-fx-01` / `dev-fx-02` são fixture, não segredo.

GetConfig lê só `store/*/current.alloy`. Token Bearer autentica; `id` escolhe o blob.

## Teste na prática — R$ 0

Não precisa Grafana Cloud, cartão, nem conta paga.

Hoje o teste é local:

1. `make serve` — liga a central
2. Noutro terminal: `make smoke` — um script **finge** ser o Alloy e pergunta o caderno
3. `./venv/bin/python hitl.py ok changesets/cs-fx-maint-01.json` — tu aprova
4. `./venv/bin/python smoke.py --id fx-02 --expect-maintenance` — a central já devolve `maintenance = "true"`

O binário real do Alloy também é grátis. Ainda **não** aponta pra este servidor: o Alloy fala Connect-RPC; esta fatia fala gRPC vanilla. Próximo passo técnico, ainda R$ 0.

O que cobraria: mandar métricas pro **Grafana Cloud** (SaaS). Não entra nesta prova.

## Fora desta fatia

IA gerando River. 75 máquinas. Alloy/Connect de verdade. Grafana Cloud.
