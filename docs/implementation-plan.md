# Review and implementation plan

## Approved scope

Fresh MySQL runtime; a small invite-only pilot; API-key-authenticated Laya decisions and hosted embeddings; Qdrant retrieval; hosted Sarvam OCR, English generation and Tamil translation; human confirmation before records are used; deferred ABDM/ABHA integration. Preserve old data separately.

## Findings and implemented fixes

| Finding | Implemented behavior |
| --- | --- |
| Documentation claimed Supabase while the backend used SQLite | SQLAlchemy/MySQL runtime with Alembic migrations; SQLite restricted to tests |
| Startup created a fake patient and clinical records | Empty runtime; operator provisions actual accounts |
| Demo login and endpoints without reliable ownership | Argon2 passwords, persisted expiring sessions, CSRF and origin checks, ownership on every clinical resource |
| Filename-based fallback fabricated clinical results | Real PDF extraction or Sarvam OCR; failures shown explicitly |
| Defaults invented dates, units, ranges and drug details | Unknown fields remain empty; manual additions/corrections supported |
| Confirmation could duplicate records | Locked confirmation, revision checks and unique SQL constraints |
| Corrections left old summaries, vectors or chat answers usable | Revision-based approval, invalidation and fresh SQL eligibility checks |
| Medication status could leave stale derived evidence | New approved revision preserves selected records and invalidates/requeues derived data |
| Background work disappeared on restart | Persisted jobs, leases, retries, heartbeat and separate extraction/index/summary state |
| Fake ABHA linking and template screens | Unsupported integration stated explicitly; focused real account/document/records/assistant/profile UI |
| Missing frontend dependencies/utilities | Replaced incomplete template with a built, linted React frontend |

## Delivery sequence

1. **Review and archive:** examine backend, frontend, providers, auth, data lifecycle and documentation; preserve existing data/source in ignored archive.
2. **SQL and identity:** implement MySQL schema/migrations and invite-only accounts; make authorization independent of client-provided patient IDs.
3. **Real document workflow:** validate uploads, queue extraction, expose actual source files, edit candidate revisions, confirm selected fields.
4. **Live records:** use approved SQL rows for history/trends and medication statuses; invalidate derived content on edits/deletion.
5. **RAG:** call authenticated Laya and embedding APIs, index approved field passages in Qdrant, restrict search by patient and SQL revision, validate cited Sarvam claims, use Laya to abstain on unsupported answers.
6. **Usable UI:** replace mocked screens, show processing/errors/empty states, implement consent and English/Tamil display.
7. **Operations:** local launch scripts, Docker definitions, backup/restore, verification suites and honest setup instructions.

These implementation stages are in the code. Live AI acceptance testing requires the operator's Laya, embedding and Sarvam API keys and processing consent. Provider integration and deployment verification are reported separately in the evaluation guide; fixture-based tests do not establish model accuracy.

## Before a wider release

Validate OCR on representative real documents, measure routing/retrieval/support decisions in both languages, test live Sarvam responses and translation preservation, provision HTTPS and secure cookies, restrict host/data access, rehearse restore with populated data, and configure monitored process restart. Complete official ABDM onboarding before implementing identity or record exchange. No medical diagnostic accuracy or regulatory certification is claimed.
