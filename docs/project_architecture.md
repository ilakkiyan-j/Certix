# Certix — Project Architecture & Technology Stack

## 1. Project Overview

**Certix** is a backend API for generating personalized certificates in bulk. A client submits one request containing certificate/event information and a list of recipients. Certix validates the input, creates a generation job, processes recipients independently, tracks progress and failures, and exposes endpoints to retrieve job results and download generated PDF certificates.

### Goals

- Generate certificates for many recipients through a single API request.
- Use one predefined certificate template.
- Validate recipient data and report invalid records clearly.
- Prevent one recipient's generation failure from unnecessarily stopping the rest of the job.
- Track job-level and recipient-level statuses.
- Allow clients to inspect progress and retrieve generated certificates.
- Provide automated tests and clear setup/API documentation.

### Out of Scope for the Initial Version

- Certificate template editor.
- Multiple template designs.
- Frontend dashboard.
- User authentication and role management, unless later required.
- Cloud deployment and distributed scaling beyond the initial worker-based design.

---

## 2. Technology Stack

| Layer | Technology | Responsibility |
|---|---|---|
| Language | Python 3.12+ | Backend implementation |
| API framework | FastAPI | REST endpoints, dependency injection, OpenAPI docs |
| Request/response validation | Pydantic | Validate and serialize API payloads |
| Relational database | PostgreSQL | Persist jobs, recipients, statuses, and file metadata |
| ORM | SQLAlchemy 2.x | Database models and queries |
| Database migrations | Alembic | Versioned schema changes |
| PDF generation | ReportLab | Render personalized certificate PDFs |
| Background queue | Redis + RQ | Queue bulk jobs and process them outside the request cycle |
| Testing | Pytest | Unit and integration tests |
| API test client | HTTPX | Exercise FastAPI endpoints in tests |
| Packaging/dependencies | `pyproject.toml` | Declare dependencies and project tooling |
| Local services | Docker Compose | Run PostgreSQL and Redis locally; optionally containerize the API and worker |
| API exploration | FastAPI Swagger UI | Explore and test endpoints at `/docs` |
| File storage (MVP) | Local filesystem | Store generated PDFs outside the source tree |
| Logging | Python `logging` | Record job lifecycle events and errors |

**Architecture choice:** use an asynchronous background worker because bulk PDF generation should not keep an HTTP request open until every certificate has finished. PostgreSQL remains the source of truth for job and recipient statuses. Redis/RQ is the proposed queue implementation and can be replaced if needed.

---

## 3. High-Level Architecture

```mermaid
flowchart TD
    Client[API Client / Swagger UI]
    API[FastAPI REST API]
    Validation[Pydantic Validation]
    Service[Job & Certificate Services]
    DB[(PostgreSQL)]
    Queue[(Redis Queue)]
    Worker[RQ Background Worker]
    Generator[ReportLab PDF Generator]
    Storage[(Local PDF Storage)]

    Client --> API
    API --> Validation
    Validation --> Service
    Service --> DB
    Service --> Queue
    Queue --> Worker
    Worker --> DB
    Worker --> Generator
    Generator --> Storage
    Worker --> DB
    API --> DB
    API --> Storage
```

### Component Responsibilities

- **API client:** submits jobs, polls progress, lists results, and downloads certificates.
- **FastAPI:** exposes versioned REST endpoints and translates application results into HTTP responses.
- **Pydantic:** validates request shape and field constraints at the API boundary.
- **Application services:** create jobs, manage state transitions, calculate progress, and coordinate certificate processing.
- **PostgreSQL:** stores durable job and per-recipient records.
- **Redis/RQ:** schedules background work and runs jobs outside the API request cycle.
- **Worker:** processes recipients independently and records success or failure for each.
- **ReportLab generator:** creates a PDF from the single predefined template and recipient-specific data.
- **Local file storage:** keeps generated PDFs; database records store the associated relative storage key/path.
- **Pytest/HTTPX:** verify behavior at service and API boundaries.

---

## 4. Suggested Repository Structure

```text
certix/
├── app/
│   ├── main.py
│   ├── api/
│   │   └── routes/
│   │       ├── health.py
│   │       ├── jobs.py
│   │       └── certificates.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── security.py
│   ├── db/
│   │   ├── base.py
│   │   ├── session.py
│   │   └── models/
│   │       ├── generation_job.py
│   │       └── certificate.py
│   ├── schemas/
│   │   ├── job.py
│   │   └── certificate.py
│   ├── services/
│   │   ├── job_service.py
│   │   ├── validation_service.py
│   │   ├── certificate_service.py
│   │   └── storage_service.py
│   ├── workers/
│   │   ├── queue.py
│   │   └── certificate_worker.py
│   └── templates/
│       └── certificate_template.py
├── tests/
│   ├── conftest.py
│   ├── test_jobs.py
│   ├── test_validation.py
│   ├── test_generation.py
│   ├── test_progress.py
│   ├── test_failures.py
│   └── test_downloads.py
├── migrations/
├── docs/
│   └── architecture.md
├── storage/
│   └── .gitkeep
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml
└── README.md
```

Create modules when their phase is reached; this structure is a target layout, not a requirement to create every file at once. Do not commit generated certificates, secrets, `.venv`, or cache files.

---

## 5. Data Model

### `generation_jobs`

One record per bulk request.

| Field | Purpose |
|---|---|
| `id` | UUID primary key |
| `status` | `queued`, `processing`, `completed`, `completed_with_errors`, or `failed` |
| `total_recipients` | Number of submitted recipient entries |
| `completed_count` | Number of successfully generated certificates |
| `failed_count` | Number of failed or invalid recipient entries |
| `created_at` | Job creation timestamp |
| `started_at` | First processing timestamp |
| `finished_at` | Job completion timestamp, nullable |

### `certificates`

One record per recipient entry, including entries that fail validation or generation.

| Field | Purpose |
|---|---|
| `id` | UUID primary key |
| `job_id` | Foreign key to `generation_jobs.id` |
| `recipient_name` | Recipient's name, nullable if invalid/missing |
| `recipient_email` | Recipient's email, nullable if invalid/missing |
| `status` | `pending`, `processing`, `completed`, or `failed` |
| `file_key` | Relative storage key/path for the generated PDF, nullable |
| `error_message` | Safe, useful failure description, nullable |
| `created_at` | Record creation timestamp |
| `completed_at` | Processing completion timestamp, nullable |

### Relationship

One `generation_jobs` row has many `certificates` rows.

### Data consistency rules

- Use UUIDs for externally visible job and certificate identifiers.
- Persist state changes; do not calculate the entire job state only in memory.
- Update counts and state transitions transactionally where practical.
- Derive progress from persisted records or keep counters synchronized with them.
- Never expose an arbitrary filesystem path to the client; resolve downloads from a stored, validated file key.
- Define duplicate-recipient behavior explicitly. The default MVP behavior should preserve each submitted entry as its own result unless requirements specify deduplication.

---

## 6. Job Lifecycle and Failure Handling

### Job status transitions

```text
queued
  |
  v
processing
  |-------------------------|
  v                         v
completed          completed_with_errors
                            |
All recipients fail          |
can result in `failed` -------+
```

Recommended final-state rules:

- `completed`: every recipient was processed successfully.
- `completed_with_errors`: at least one recipient succeeded and at least one failed.
- `failed`: the job could not be executed as a whole, or all recipients failed, according to the documented policy.
- A job with zero valid recipients should still finish with clear per-recipient errors and a deterministic final status.

### Recipient status transitions

```text
pending -> processing -> completed
                     \-> failed
```

### Failure isolation

1. Validate each recipient independently after validating the overall request structure.
2. Mark invalid recipient entries as failed with a clear reason.
3. Process each valid recipient inside its own error boundary.
4. Save the generated PDF and then persist its storage key and completed status.
5. On an individual failure, record the error and continue with the next recipient.
6. Log unexpected exceptions with job and certificate IDs; do not expose stack traces or secrets in API responses.

### Queue and worker reliability

- Commit the job and recipient rows before enqueueing work.
- Consider the failure window between database commit and queue enqueue; for this assignment, document it and implement recovery or a small dispatch retry mechanism.
- Make processing idempotent where possible so a retried task does not create uncontrolled duplicate files or records.
- Define retry limits and how interrupted `processing` records are recovered.
- Keep PostgreSQL as the source of truth; Redis is for dispatching work, not the only record of job status.

---

## 7. API Contract

Use the prefix `/api/v1`.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/jobs` | Submit a bulk generation job |
| `GET` | `/api/v1/jobs/{job_id}` | Retrieve job status and progress |
| `GET` | `/api/v1/jobs/{job_id}/certificates` | List recipient results |
| `GET` | `/api/v1/certificates/{certificate_id}/download` | Download a generated PDF |
| `GET` | `/health` | Check service health |

### Create job request example

```json
{
  "event_name": "AI Workshop 2026",
  "completion_date": "2026-10-10",
  "recipients": [
    {
      "name": "Arun Kumar",
      "email": "arun@example.com"
    },
    {
      "name": "Priya Sharma",
      "email": "priya@example.com"
    }
  ]
}
```

### Create job response example

Return `202 Accepted` once the request has been accepted and persisted.

```json
{
  "job_id": "generated-uuid",
  "status": "queued",
  "total_recipients": 2,
  "completed": 0,
  "failed": 0
}
```

### Job status response example

```json
{
  "job_id": "generated-uuid",
  "status": "processing",
  "total_recipients": 100,
  "processed": 45,
  "completed": 42,
  "failed": 3,
  "progress_percentage": 45
}
```

Examples are illustrative. Define the exact schemas, status semantics, and error format in the Pydantic models and API documentation.

### API behavior

- Return `404` for unknown job or certificate IDs.
- Return a suitable `4xx` response for invalid request structure.
- Return `202` for an accepted asynchronous job.
- Include failed recipient details in the results endpoint.
- Do not expose a download link until a certificate has been successfully generated.
- Restrict downloads to records belonging to the requested certificate ID and a safe storage key.

---

## 8. Certificate Generation and Storage

- Use ReportLab to create PDF certificates from one predefined template.
- Include recipient name, event/course name, completion date, and any agreed certificate identifier.
- Support long and Unicode names with appropriate fonts and text layout.
- Use a stable unique filename or storage key, rather than using an untrusted recipient name as a path.
- Store files in a configurable local directory for the MVP.
- Keep storage logic behind `storage_service.py` so object storage can be introduced later.
- Check file existence and handle missing files gracefully during downloads.
- Avoid committing generated PDFs to source control.

---

## 9. Testing Strategy

Use Pytest for unit tests and HTTPX/FastAPI's test client for API integration tests.

Required test coverage:

- Job creation and database persistence.
- Request and recipient validation.
- Successful PDF generation and personalized content.
- Job status and progress calculation.
- Individual recipient failure without stopping other recipients.
- Listing results, including failed entries.
- Successful certificate download.
- Unknown IDs and missing-file handling.

Additional reliability tests:

- Empty recipient list and malformed input.
- Unicode and unusually long recipient names.
- Duplicate recipients.
- Two jobs processing concurrently.
- Worker exception and retry behavior.
- Consistency between recipient statuses, job counters, and final job status.

Use temporary directories and isolated test databases where practical. Tests should not depend on a developer's existing database or generated files.

---

## 10. Configuration and Local Development

### `.env.example`

Include placeholders for configuration such as:

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+psycopg://certix:certix@localhost:5432/certix
REDIS_URL=redis://localhost:6379/0
CERTIFICATE_STORAGE_DIR=./storage/generated
LOG_LEVEL=INFO
```

These are development examples only. Use local credentials for development, keep real secrets out of Git, and validate required configuration at startup.

### Docker Compose services

- `api`: FastAPI application.
- `worker`: RQ worker running the certificate processing function.
- `postgres`: relational database.
- `redis`: background job queue.

The API and worker should share the same configuration and certificate storage volume for the local-filesystem MVP.

---

## 11. Documentation Deliverables

### `README.md`

Must explain:

- Project overview and scope.
- Prerequisites and setup.
- Environment configuration.
- Database migrations.
- How to run the API and worker.
- How to run tests.
- API request/response examples.
- How to inspect job progress and download certificates.
- Key design decisions and known limitations.

### `docs/architecture.md`

This document should capture:

- Component diagram and technology stack.
- Database schema and relationships.
- Job and recipient state transitions.
- Queue and worker responsibilities.
- Failure isolation, retry, and recovery decisions.
- API design and storage strategy.

---

## 12. Definition of Done

Certix is ready for submission when:

- A single request can submit many recipients.
- Each recipient has a durable and inspectable outcome.
- Valid certificates are generated as PDFs.
- One recipient's failure does not stop other recipients.
- Job status and progress accurately reflect persisted results.
- Generated certificates can be downloaded safely.
- All mandatory automated tests pass.
- A fresh checkout can be configured and run using the README.
- The implementation and key trade-offs can be explained and modified during an interview.

---

## 13. Implementation Order

1. Architecture and schemas.
2. FastAPI foundation and database migrations.
3. Job creation and recipient records.
4. PDF generation.
5. Background worker and isolated failure handling.
6. Status, results, and download endpoints.
7. Required tests and reliability checks.
8. README, Docker Compose, and final submission review.

**Guiding principle:** finish the required functionality before adding optional features. Keep the first version understandable, testable, and reliable.
