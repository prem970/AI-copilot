# Operator guide

## Accounts and service management

Run from the root with `PYTHONPATH=backend`. `python -m app.cli create-user --email EMAIL --name NAME` provisions an account; `reset-password --email EMAIL` prompts privately and expires sessions; `disable-user --email EMAIL` disables access and expires sessions. Users can create an account from the sign-in screen with their name, email, and a matching password of at least 12 characters. Registration signs them in, rejects duplicate emails without changing existing accounts, and limits attempts by IP. There is no default account or self-service password recovery. The CLI should run only under the operator's OS account.

On Windows use the prepared `.venv/Scripts/python.exe`. `scripts/start_local.py` launches API, worker, portable Qdrant and frontend invisibly on loopback. `--services api worker` selects services. `scripts/stop_local.py` verifies stored PIDs against workspace and command before stopping them. MySQL is independent; bootstrap starts it after reboot. These are local launch helpers, not a monitored production supervisor.

Inspect `.runtime/*.stderr.log` after a startup failure. `/ready` checks SQL and worker heartbeat, `/health` checks API liveness, and port 6333 `/healthz` checks portable vector availability. Readiness includes nonsecret configuration flags for all three AI keys. Missing credentials are explicit and do not block manual records. AI calls require internet access and funded provider accounts; no model files or GPU are needed. Run `scripts/verify_ai_apis.py` for a live smoke (uses credits and synthetic text), optionally `--ocr-file PATH` to authorize sending a real file for document-extraction verification.

## Backup and restore

Stop API/worker writes before backup so SQL and source files describe the same point in time. Keep MySQL running. Run:

```powershell
.venv/Scripts/python.exe scripts/stop_local.py --services api worker
.venv/Scripts/python.exe scripts/backup.py
.venv/Scripts/python.exe scripts/start_local.py --services api worker
```

The backup ZIP contains a transactional SQL dump, private source files and SHA-256 checksums. It excludes `.env`, provider keys, archives and vector storage. **The ZIP is not encrypted**: restrict filesystem access and use your organization's encrypted backup destination. Keep keys and connection configuration separately. Take backups on a regular schedule; no scheduler is automatically installed.

Provision a completely empty MySQL database and empty source-file directory. Set `RESTORE_DATABASE_URL` privately, then run `scripts/restore.py BACKUP.zip --storage DIRECTORY`. Restore refuses any existing database tables or source files and verifies archive paths/checksums. Change `DATABASE_URL` and `STORAGE_DIR` to the restored targets, migrate if needed, and restart services. Reset user passwords/sessions if restoring onto a different security boundary. After obtaining external-processing consent, reindex every approved document using its authenticated `/documents/{id}/index` endpoint; Qdrant can be rebuilt from SQL. Archive retention is independent of document deletion: expired backups/archives must also be removed according to your retention policy.

`scripts/verify_backup.py` rehearses backup/restore against a dedicated empty `health_copilot_restore_verify` database and compares table counts; it never overwrites the active pilot database. The rehearsal contains whatever real pilot backup exists, so protect its files/database too. Use a populated rehearsal before relying on disaster recovery for regular use.

## Docker

`compose.yaml` defines MySQL, official Qdrant, API, worker and an Nginx-served frontend. Generate separate `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` and `QDRANT_API_KEY` values in `.env`; hex secrets simplify database URL encoding. Set `LAYA_API_KEY`, `GEMINI_API_KEY` and `SARVAM_API_KEY` for AI processing. Run `docker compose up --build -d`, then provision an account with `docker compose exec api python -m app.cli create-user ...`. Only web port 8080 is published on loopback. Persistent volumes retain SQL, documents and vectors.

Docker is not installed in the current workspace environment, so container builds/startup remain unverified here. Do not assume a Compose definition proves a deployment works.

## Hosting beyond this machine

Provide HTTPS and set `ENVIRONMENT=production`, `COOKIE_SECURE=true`, and a precise `CORS_ORIGINS` allowlist. Use a trusted reverse proxy and a supervised worker; add monitoring for failures and queued jobs. Keep database and Qdrant off the public network. Configure host/volume encryption, least-privilege credentials, backup retention and operator access. Confirm provider data-handling terms and the intended health-data workflow before inviting people. Rehearse a populated restore and execute the live AI evaluations before expanding the pilot.
