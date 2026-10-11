# API map

The running API exposes full OpenAPI documentation at `/docs`. All clinical endpoints require the server-issued session cookie. Mutations also require the `X-CSRF-Token` returned by sign-in/session and an allowed browser origin. Ownership comes from the authenticated account; patient identifiers supplied by clients cannot override it.

| Workflow | Endpoints under `/api/v1` |
| --- | --- |
| Session | `POST /auth/login`, `GET /auth/session`, `POST /auth/logout` |
| Profile and consent | `GET/PATCH /patient/me` |
| Upload and list | `POST /documents` (multipart file, 202), `GET /documents?offset=0&limit=50` |
| Processing and source | `GET /documents/{id}`, `/status`, `/jobs`, `/file`; `POST /documents/{id}/process` retries failed extraction |
| Review | `GET/PATCH /documents/{id}/extraction`, `POST /documents/{id}/confirm` |
| Summary and index | `GET /documents/{id}/summary?lang=en|ta`, `POST /documents/{id}/summary`, `POST /documents/{id}/index` |
| Delete | `DELETE /documents/{id}` |
| Reviewed data | `GET /observations`, `GET /observations/trends`, `GET /medications`, `PATCH /medications/{id}`, `GET /timeline` |
| Assistant | `GET/POST /rag/conversations`, `GET/POST /rag/conversations/{id}/messages` |
| ABHA | `GET /abha/status` reports unavailable |

Extraction edits and confirmation include the current `revision`. Confirmation includes explicit `observation_ids`, `medication_ids` and `active_medications`, or `confirm_all=true`. Unknown IDs, empty selection and stale revisions are rejected. Records are not written before confirmation. Editing approved fields or medication status advances the revision and invalidates derived results.

Sign-in returns 401 for bad credentials and 429 when throttled. Unauthorized ownership returns 404. Missing consent, stale revisions, pending summaries and invalid review state return 409. Unsupported/mismatched files return 400, oversized files 413, malformed payloads 422, and SQL failure 503. AI failure is returned as an explicit assistant `unavailable` status, with no fabricated answer.

All AI requests originate on the backend: Laya `POST https://laya-model.com/v1/decide` uses `Authorization: Bearer LAYA_API_KEY`; Gemini `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents` uses `x-goog-api-key: GEMINI_API_KEY`; Sarvam uses `api-subscription-key: SARVAM_API_KEY`. Gemini requests use `RETRIEVAL_DOCUMENT` for reviewed fields, `RETRIEVAL_QUERY` for questions, and `outputDimensionality: 1536`. Keys are never browser parameters or URL query strings. Indexing, assistant answers, summaries and scanned OCR require external-processing consent. The portable vector service requires `api-key: QDRANT_API_KEY` and stays on the private network. There is no local model endpoint.
