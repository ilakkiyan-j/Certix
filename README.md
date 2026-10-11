# Certix — Bulk Certificate Generator Backend API

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![ORM](https://img.shields.io/badge/SQLAlchemy-2.0%2B-red.svg)](https://www.sqlalchemy.org/)
[![Queue](https://img.shields.io/badge/Redis%20%2B%20RQ-2.0%2B-CC0000.svg)](https://python-rq.org/)
[![PDF Engine](https://img.shields.io/badge/ReportLab-4.2%2B-orange.svg)](https://www.reportlab.com/)
[![Tests](https://img.shields.io/badge/pytest-40%20passed-brightgreen.svg)]()
[![Code Style](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)

Certix is a production-grade, asynchronous backend API built with **FastAPI**, **SQLAlchemy 2.x**, **PostgreSQL**, **Redis + RQ**, and **ReportLab**. It accepts bulk certificate requests, validates recipient entries, isolates individual recipient generation failures, tracks processing progress in real time, and securely delivers personalized PDF certificates.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    Client[API Client / Frontend] -->|1. POST /api/v1/jobs| API[FastAPI Application]
    API -->|2. Transactional Commit| DB[(PostgreSQL Database)]
    API -->|3. Enqueue job_id| Queue[Redis Queue: certix_jobs]
    API -->|4. 202 Accepted + status_url| Client

    subgraph Background RQ Worker
        Queue -.->|5. Dequeue job_id| Worker[Certificate Worker]
        Worker -->|6. Fetch pending certs| DB
        Worker -->|7. Render PDF Template| ReportLab[ReportLab PDF Engine]
        ReportLab -->|8. Atomic write| Storage[(Local Storage / StorageService)]
        Worker -->|9. Isolated Status Commit| DB
        Worker -->|10. Reconcile Counters & Status| DB
    end

    Client -->|11. GET /api/v1/jobs/{id}| API
    Client -->|12. GET /api/v1/jobs/{id}/certificates| API
    Client -->|13. GET /api/v1/certificates/{id}/download| API
    API -->|14. Safe Stream PDF| Storage
    API -->|15. application/pdf| Client
```

---

## 📜 Generated Certificate Preview

Certix dynamically compiles landscape A4 certificates in vector PDF format featuring double gold borders, geometric corner ornaments, automatic typography scaling, and a circular verification seal:

<p align="center">
  <img src="docs/images/certificate_sample.png" alt="Certix Sample Certificate" width="850" />
</p>

---

## ✨ Key Features

- **Asynchronous Bulk Processing:** Decoupled FastAPI request handlers return immediate `202 Accepted` responses while Redis + RQ background workers process PDF generation out-of-band.
- **Fault Isolation & Partial Failures:** Each recipient certificate is rendered and committed within its own isolated transaction boundary. Malformed emails or individual rendering errors never cancel or block valid recipients in the batch.
- **Dynamic Certificate Typography:** Built with ReportLab using dynamic font scaling (`28pt` -> `18pt`) to gracefully render arbitrarily long names and full Unicode international characters without text clipping.
- **Strict Storage Jail Security:** File keys are strictly validated with server-generated UUIDs against directory-traversal attacks (`InvalidPathError`).
- **Comprehensive Lifecycle State Machine:**
  - **Job Status:** `queued` → `processing` → `completed` | `completed_with_errors` | `failed`.
  - **Certificate Status:** `pending` → `processing` → `completed` | `failed`.
- **40+ Automated Unit & Integration Tests:** 100% pass rate in sub-second test runs covering persistence, generation, queues, retrieval, concurrency, and crash recovery.

---

## 🛠️ Technology Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Language** | Python 3.12+ | Modern type annotations, async/await syntax |
| **API Framework** | FastAPI | High-performance async REST framework |
| **Database ORM** | SQLAlchemy 2.x (Async + Sync) | Declarative 2.0 mapping with psycopg driver |
| **Database** | PostgreSQL 16 / SQLite (testing) | Relational persistence with check constraints |
| **Migrations** | Alembic | Database schema versioning and DDL generation |
| **Task Queue** | Redis 7 + RQ (Redis Queue) | Background worker execution and task management |
| **PDF Generation** | ReportLab 4.2+ | Vector graphics, double borders, dynamic scaling |
| **Testing** | Pytest, pytest-asyncio, pytest-cov | Sub-second deterministic test suite |
| **Linter & Formatter** | Ruff | Ultra-fast linting and formatting compliance |
| **Containerization** | Docker & Docker Compose | Containerized API, Worker, PostgreSQL, and Redis |

---

## ⚙️ Environment Variables

Create a `.env` file in the project root (or copy from `.env.example`):

```env
# Application Settings
APP_NAME=Certix
APP_ENV=development
DEBUG=false
LOG_LEVEL=INFO

# Networking
HOST=0.0.0.0
PORT=8000
API_V1_PREFIX=/api/v1

# PostgreSQL Database
DATABASE_URL=postgresql+psycopg://certix:certix@localhost:5432/certix

# Redis Task Queue
REDIS_URL=redis://localhost:6379/0
QUEUE_NAME=certix_jobs

# Certificate Output Storage
CERTIFICATE_STORAGE_DIR=./storage/generated
```

---

## 🚀 Quick Start & Installation

### Option 1: Docker Compose (Recommended)

Run the complete multi-service stack (API, Background Worker, PostgreSQL, Redis) with a single command:

```bash
docker compose up --build
```

> **Note:** Database migrations (`alembic upgrade head`) are automatically applied by the `api` container on startup before launching the Uvicorn server.

- API Server: `http://localhost:8000`
- Interactive API Docs (Swagger UI): `http://localhost:8000/docs`
- ReDoc Reference: `http://localhost:8000/redoc`

---

### Option 2: Local Setup (Virtual Environment)

#### 1. Clone and Navigate
```bash
git clone <repository-url>
cd Certix
```

#### 2. Create and Activate Virtual Environment
Using `uv`:
```bash
uv venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Or using standard Python `venv`:
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
pip install -e ".[dev]"
```

#### 3. Run Database Migrations
```bash
alembic upgrade head
```

#### 4. Start Infrastructure (PostgreSQL + Redis)
If using Docker for databases only:
```bash
docker compose up postgres redis -d
```

#### 5. Start API Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 6. Start Background Worker (in a separate terminal)
```bash
python -m app.workers.cli
```

---

## 📖 API Reference & Usage

### 1. Health Check
Check API availability and service health.

```bash
curl -X GET "http://localhost:8000/health"
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "app_name": "Certix",
  "version": "0.1.0",
  "environment": "development"
}
```

---

### 2. Submit Bulk Generation Job
Submits a batch of recipients for asynchronous certificate generation.

```bash
curl -X POST "http://localhost:8000/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "Cloud Architecture Masterclass 2026",
    "completion_date": "2026-10-15",
    "recipients": [
      { "name": "Alice Wonderland", "email": "alice@example.com" },
      { "name": "François René", "email": "francois@example.org" },
      { "name": "Invalid Recipient", "email": "bad-email-format" }
    ]
  }'
```

**Response (202 Accepted):**
```json
{
  "job_id": "a3f124b8-2c49-41ef-b924-f7b57223b102",
  "status": "queued",
  "total_recipients": 3,
  "completed": 0,
  "failed": 1,
  "status_url": "/api/v1/jobs/a3f124b8-2c49-41ef-b924-f7b57223b102"
}
```

---

### 3. Check Job Status & Progress
Poll the job status, processed counts, and progress percentage.

```bash
curl -X GET "http://localhost:8000/api/v1/jobs/a3f124b8-2c49-41ef-b924-f7b57223b102"
```

**Response (200 OK):**
```json
{
  "job_id": "a3f124b8-2c49-41ef-b924-f7b57223b102",
  "status": "completed_with_errors",
  "total_recipients": 3,
  "processed": 3,
  "completed": 2,
  "failed": 1,
  "progress_percentage": 100.0,
  "created_at": "2026-10-10T01:30:00Z",
  "started_at": "2026-10-10T01:30:01Z",
  "finished_at": "2026-10-10T01:30:03Z"
}
```

---

### 4. List Job Certificates (Paginated)
Fetch certificate records, recipient details, download URLs, and failure errors.

```bash
curl -X GET "http://localhost:8000/api/v1/jobs/a3f124b8-2c49-41ef-b924-f7b57223b102/certificates?limit=50&offset=0"
```

**Response (200 OK):**
```json
{
  "job_id": "a3f124b8-2c49-41ef-b924-f7b57223b102",
  "total": 3,
  "limit": 50,
  "offset": 0,
  "results": [
    {
      "certificate_id": "79b4de45-7186-4e58-86d1-4db8bfba5299",
      "recipient_name": "Alice Wonderland",
      "recipient_email": "alice@example.com",
      "status": "completed",
      "download_url": "/api/v1/certificates/79b4de45-7186-4e58-86d1-4db8bfba5299/download",
      "error": null
    },
    {
      "certificate_id": "f8a0021b-64a8-41ec-b8f1-e7373f78a2e1",
      "recipient_name": "François René",
      "recipient_email": "francois@example.org",
      "status": "completed",
      "download_url": "/api/v1/certificates/f8a0021b-64a8-41ec-b8f1-e7373f78a2e1/download",
      "error": null
    },
    {
      "certificate_id": "21e42e47-e23a-4467-bc18-2adbc286c04f",
      "recipient_name": "Invalid Recipient",
      "recipient_email": "bad-email-format",
      "status": "failed",
      "download_url": null,
      "error": {
        "code": "INVALID_RECIPIENT_DATA",
        "message": "Invalid recipient email address: The email address is not valid."
      }
    }
  ]
}
```

---

### 5. Download Certificate PDF
Streams the physical PDF binary file directly to disk.

```bash
curl -X GET "http://localhost:8000/api/v1/certificates/79b4de45-7186-4e58-86d1-4db8bfba5299/download" \
  --output certificate.pdf
```

**HTTP Status Codes:**
- `200 OK`: Returns binary stream with `Content-Type: application/pdf` and `Content-Disposition: attachment; filename="certificate_<uuid>.pdf"`.
- `404 Not Found`: Certificate record or physical file missing (`CERTIFICATE_NOT_FOUND` / `FILE_NOT_FOUND`).
- `409 Conflict`: Certificate is not ready (`CERTIFICATE_NOT_READY`) or generation failed (`CERTIFICATE_FAILED`).

---

## 🧪 Testing & Verification

Run the full automated test suite with coverage:

```bash
# Run pytest with coverage report
pytest -v --cov=app --cov-report=term-missing
```

Run code formatting and style linters:

```bash
# Lint code
ruff check app tests

# Check formatting
ruff format --check app tests
```

### Test Suite Structure
```text
tests/
├── conftest.py              # Test database engines & client fixtures
├── test_health.py           # Health endpoint tests
├── test_database.py         # Model constraints & cascade delete tests
├── test_validation.py       # Top-level Pydantic validation tests
├── test_jobs.py             # Job submission & isolation tests
├── test_generation.py       # ReportLab PDF & StorageService tests
├── test_worker.py           # RQ Worker execution & reconciliation tests
├── test_retrieval.py        # Status, pagination & download tests
└── test_e2e_reliability.py  # Full lifecycle E2E & concurrency tests
```

---

## ⚖️ Design Trade-offs & Decisions

1. **Dual Engine Architecture (Async API + Sync Workers):**
   - FastAPI request handlers operate asynchronously (`AsyncSession`) with non-blocking I/O.
   - RQ workers run in separate worker processes using synchronous sessions (`Session`), preventing greenlet context conflicts while maintaining optimal throughput.
2. **Atomic Storage Movement:**
   - PDFs are rendered to isolated temporary files first and only moved to `storage/generated/certificates/<uuid>.pdf` upon non-zero byte size verification.
3. **Fault Isolation vs. Immediate Rejection:**
   - Malformed top-level requests return HTTP 422 immediately.
   - Individual recipient validation errors (e.g. malformed email) are preserved as `failed` records with error codes in the database, allowing valid recipients in the batch to proceed unimpeded.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) — see the [LICENSE](LICENSE) file for details.
