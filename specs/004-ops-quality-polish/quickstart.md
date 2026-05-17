# Quickstart — 004-ops-quality-polish

Four end-to-end smoke scenarios. Each maps to one user story.

**Prerequisites**:
- Features 001 / 002 / 003 are merged on `main` and the stack is up: `docker compose up -d`.
- `.env` now also contains `MASTER_KEY=…` (any 32-byte url-safe-base64 string; generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
- Recreate the `api` container after editing `.env`: `docker compose up -d --force-recreate api`.

---

## Scenario A — Ping job round-trip (US1)

**Steps**:

```bash
JOB_ID=$(curl -sS -X POST http://localhost:8000/api/jobs/ping \
              -H 'Content-Type: application/json' -d '{}' \
              | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "enqueued $JOB_ID"

for _ in 1 2 3 4 5; do
  sleep 1
  STATUS=$(curl -sS http://localhost:8000/api/jobs/$JOB_ID | python3 -m json.tool)
  echo "$STATUS"
  echo "$STATUS" | grep -q '"status": "complete"' && break
done
```

**Expected**: within 5 s the polled response carries `"status": "complete"` and `"result": {"stamped_at": "..."}`.

**Worker badge check**:

```bash
curl -sS http://localhost:8000/healthz | python3 -m json.tool
```

`worker` should read `"ok"`.

---

## Scenario B — Settings save + immediate provider switch (US2)

**Steps**:

1. Confirm a baseline:

   ```bash
   curl -sS http://localhost:8000/api/settings | python3 -m json.tool
   ```

   `active_llm_provider` reads `"openai"`, `credentials.openai_api_key.set` is `true` (assuming you set it in `.env`), `credentials.anthropic_api_key.set` is `false`.

2. Provide an Anthropic key and switch providers:

   ```bash
   curl -sS -X POST http://localhost:8000/api/settings \
        -H 'Content-Type: application/json' \
        -d '{"active_llm_provider":"anthropic","anthropic_api_key":"sk-ant-..."}'
   ```

   The response is the same shape as `GET`, but `active_llm_provider` is now `"anthropic"` and `credentials.anthropic_api_key.set` is `true` with a `…xxxx` fingerprint.

3. **Without restarting any container**, run the demo PR through review (Scenario C of 003):

   ```bash
   curl -sS -X POST http://localhost:8000/api/review \
        -H 'Content-Type: application/json' \
        -d '{"pr_url":"https://github.com/tarasIvanov/codesensei/pull/8"}' \
        | python3 -m json.tool
   ```

   The response carries `"provider": "anthropic"`.

**Sanity check** — without `MASTER_KEY` set:

```bash
curl -sS -X POST http://localhost:8000/api/settings \
     -H 'Content-Type: application/json' \
     -d '{"openai_api_key":"sk-..."}' \
     -w '\nHTTP %{http_code}\n'
```

Returns `503` with `category: "settings_locked"` and a message about `MASTER_KEY`.

---

## Scenario C — Demo PR re-run with calibrated severities (US3)

**Steps**:

1. Re-run the demo PR (URL: `https://github.com/tarasIvanov/codesensei/pull/8`) through `/review`.
2. In the response findings list, the hardcoded `ADMIN_API_KEY` finding, the SQL-injection finding, and the `eval(expression)` finding all carry `"severity": "blocker"`.
3. The reported `line` values land **within ±1** of the actual file lines (14, ~25, ~46 in the toy file).

**Comparison vs baseline (post-003 reviewer):** previously, all three landed as `"major"` with line numbers drifted ~6 lines.

---

## Scenario D — Worker-down badge demo (US1 edge case)

```bash
docker compose stop worker
sleep 65  # >= worker_heartbeat_stale_s (default 60)
curl -sS http://localhost:8000/healthz | python3 -m json.tool
```

`worker` reads `"down"`. `status` still reads `"ok"` and `failing[]` (if present) does **not** include `"worker"`.

Bring it back:

```bash
docker compose start worker
sleep 5
curl -sS http://localhost:8000/healthz | python3 -m json.tool   # worker: ok
```

---

## Out of scope (do **not** test for these)

- **Review-as-job**: `POST /api/review` is still synchronous. Submitting a review does not enqueue an arq job in this feature.
- **GitHub webhook**: still not in scope; that's 005+.
- **Settings audit log**: deliberate omission (single-tenant, no compliance need).
- **Key rotation tooling**: rotating `MASTER_KEY` requires the operator to re-enter affected credentials. Automated rotation is 006+.
