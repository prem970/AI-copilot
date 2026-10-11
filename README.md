# Personal Health Copilot — private pilot

A real account-based prototype for uploading health documents, reviewing extracted fields, storing confirmed records in MySQL, tracking results, and asking cited questions. The runtime starts empty. There is no demo login, seeded patient, simulated ABHA connection, or fabricated OCR fallback.

## Start on this Windows machine

The virtual environment, frontend packages, and portable MySQL installation have been prepared. Run from the project root in PowerShell:

```powershell
$env:PYTHONPATH = 'backend'
.venv/Scripts/python.exe scripts/bootstrap_mysql.py
.venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
.venv/Scripts/python.exe scripts/start_local.py
```

Open **http://127.0.0.1:5173** and choose **Create account**. Enter your name, email, and a password of at least 12 characters, then confirm the password. Account creation signs you in automatically. Use the same email and password to sign in again; existing accounts and records are preserved. There is no default password. Operators can also provision accounts using `python -m app.cli create-user --email EMAIL --name NAME`, which asks for a password privately.

Add these provider credentials to the root `.env` (backend only):

| Key | Features |
| --- | --- |
| `LAYA_API_KEY` | Laya routing, relevance and answer-support decisions at [laya-model.com](https://laya-model.com/docs/api) |
| `GEMINI_API_KEY` | Reviewed-record and question embeddings through [Google Gemini](https://ai.google.dev/gemini-api/docs/embeddings) |
| `SARVAM_API_KEY` | Scanned-document OCR, summaries, cited answers and Tamil translation |

All AI runs through authenticated HTTPS APIs. There are no local model weights, model downloads, or anonymous/demo fallbacks. Gemini embeddings use `gemini-embedding-001`, 1536 dimensions, and the native Google API with a server-side `x-goog-api-key` header. Get a Gemini key from [Google AI Studio](https://aistudio.google.com/api-keys) and put it in `.env` as `GEMINI_API_KEY`. Settings are shown in `.env.example`. Laya uses `multilingual` explicitly for English and Tamil. Then restart the API and worker:

```powershell
.venv/Scripts/python.exe scripts/stop_local.py --services api worker
.venv/Scripts/python.exe scripts/start_local.py --services api worker
```

Enable external processing in **Profile & consent** before using any AI feature. Text PDFs, manual review, records, and trends work without it. Migration `0003_hosted_ai_consent` clears old Sarvam-only consent; `0004_gemini_embeddings` refreshes consent when switching the embedding recipient to Google. Existing users must accept the updated provider notice. After enabling consent, use **Index / retry search** on previously confirmed documents to build the new Gemini index; old embedding vectors are never searched by this configuration. Run `scripts/verify_ai_apis.py` after adding keys to check live integrations with synthetic text (uses provider credits).

## Regular use

1. Upload the actual PDF, PNG, or JPEG (up to 15 MB; PDFs up to 100 pages).
2. Wait for extraction and open **Review**. Compare with the original, correct fields, and manually add any missed results or prescriptions.
3. Select the records to confirm. Mark a medication active only if you currently take it.
4. View confirmed records and trends. English/Tamil summaries and vector indexing run independently in durable jobs.
5. Ask the assistant about reviewed records. Answers require current source citations and a Laya support decision; insufficient evidence and service outages appear explicitly.

The parser recognizes a limited set of common laboratory names and prescription patterns. It does not infer missing dates, ranges, doses, or diagnoses. ABHA/ABDM remains unavailable pending official integration.

## New installation

Use Python 3.10+ and Node 24. Create `.venv`, install `backend/requirements.txt` and `backend/requirements-test.txt`, and run `npm ci` in `frontend`. The Windows bootstrap downloads official MySQL 8.4.11 and creates private app/verification databases on loopback port 3307. On another system, provision MySQL yourself, copy `.env.example` to `.env`, set random credentials/tokens, and apply migrations before creating accounts.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt -r backend/requirements-test.txt
```

Keep `.env`, `.runtime`, `.tools`, `data`, and `archive` private. Original source and existing data were preserved under `archive/pre-pilot-20261011`; archived records are never served by the new app. SQLite is accepted only in isolated tests. Runtime SQL storage is MySQL, with no Supabase dependency.

## Verification and operations

```powershell
.venv/Scripts/python.exe scripts/verify_mysql.py
.venv/Scripts/python.exe scripts/verify_vectors.py
.venv/Scripts/python.exe scripts/verify_ai_apis.py
```

In `frontend`, run `npm run lint`, `npm run build`, and `npm test` (install Chromium with `npm exec playwright install chromium` first). Browser tests use a separate test database, account, and storage directory. Provider simulations exist only in tests.

`/health` checks API liveness. `/ready` checks MySQL/schema and a recent worker heartbeat; it reports whether Laya, embeddings and Sarvam have keys. It does not certify provider availability. Logs and process IDs are in `.runtime`; use `scripts/stop_local.py` to stop app services. MySQL persists separately and `bootstrap_mysql.py` starts it again after a reboot.

See [implementation review](docs/implementation-plan.md), [architecture](docs/architecture.md), [operations and backup](docs/operations.md), and [evaluation](docs/ai-evaluation.md). Docker Compose definitions are included for an isolated deployment, but Docker was unavailable on this machine and those images have not been executed here. This is an informational private pilot; public production deployment requires the work listed in the operations guide.
