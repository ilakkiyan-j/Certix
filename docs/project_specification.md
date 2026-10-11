# Certix — Project Specification

**Project name:** Certix  
**Project type:** Backend API  
**Primary purpose:** Bulk certificate generation and retrieval  
**Status:** Initial specification for implementation

---

## 1. Purpose

Certix enables an organization to generate personalized certificates for a large number of participants after an event, course, or similar activity.

A client submits one API request containing certificate/event information and multiple recipients. The backend validates the request, creates a generation job, generates a PDF certificate for each valid recipient using one predefined template, tracks each result, and allows clients to inspect progress and retrieve generated certificates.

The system must support bulk generation rather than requiring one API request per certificate.

## 2. Objectives

Certix must:

1. Accept a bulk certificate generation request.
2. Validate recipient data and identify invalid entries.
3. Generate personalized certificates using a single predefined template.
4. Track the status of the overall generation job.
5. Track the status and outcome of each recipient's certificate.
6. Expose an API for checking progress and retrieving results.
7. Allow successfully generated certificates to be downloaded.
8. Continue processing other recipients when one certificate fails.
9. Include automated tests and setup/API documentation.

## 3. Scope

### 3.1 In scope

- Python backend application.
- REST API built with FastAPI.
- Relational database persistence.
- Bulk job creation.
- Recipient-level validation and status tracking.
- PDF generation using ReportLab.
- Background processing using Redis and RQ.
- Job progress and result retrieval.
- Downloading generated certificate PDFs.
- Automated unit and integration tests.
- Local development configuration and documentation.

### 3.2 Out of scope for the initial version

- Certificate template editor.
- Support for multiple certificate designs.
- Frontend dashboard or user interface.
- Authentication and role-based access control unless later required.
- Production cloud deployment.
- Advanced analytics, email delivery, or public certificate verification.

Optional features must not delay completion of the required functionality.

## 4. Users and Primary Workflow

### Primary user

An API client representing an organization or application that needs to issue certificates to multiple recipients.

### Workflow

1. The client submits a bulk generation request.
2. Certix validates the request structure and recipient entries.
3. Certix persists a generation job and a record for each recipient.
4. Certix queues the work for background processing.
5. The worker processes each recipient independently.
6. Certix stores each generated PDF and records the corresponding result.
7. The client checks job progress and retrieves the recipient results.
8. The client downloads certificates that completed successfully.

## 5. Functional Requirements

### FR-01 — Create a bulk job

The API must accept a single request containing shared certificate/event details and a list of recipients.

**Expected result:** return a job identifier and initial status after the job has been accepted and persisted.

### FR-02 — Validate input

The API must validate the request structure and required fields. Invalid recipient data must be identified and reported clearly.

The implementation must define whether structurally invalid requests are rejected as a whole or whether individual invalid recipients are retained as failed results. The proposed default is to reject malformed top-level payloads while recording recipient-level validation failures individually.

### FR-03 — Generate certificates

The system must generate a PDF for every valid recipient using one predefined certificate template. Each PDF must contain recipient-specific details and the shared event/course details provided in the request.

### FR-04 — Process recipients independently

A failure while generating one recipient's certificate must not unnecessarily prevent other valid recipients in the same job from being processed.

### FR-05 — Track recipient results

Each submitted recipient entry must have a persistent result indicating whether processing is pending, in progress, successful, or failed.

### FR-06 — Track job progress

The API must expose job status, total recipient count, processed count, successful count, failed count, and progress percentage.

The exact meaning of “processed” and the rules for final job statuses must be documented and consistently implemented.

### FR-07 — List job results

The API must return the results associated with a job, including successful certificate identifiers and useful failure information for unsuccessful entries.

### FR-08 — Download certificates

The API must allow a client to download a successfully generated certificate PDF. Unknown identifiers and unavailable files must be handled safely.

### FR-09 — Persist data

Job and recipient statuses must be stored in a relational database so they remain available after an API process restart.

### FR-10 — Document the project

The repository must include setup instructions, run instructions, test instructions, API usage examples, certificate retrieval instructions, and key design decisions.

## 6. Non-Functional Requirements

### NFR-01 — Bulk-oriented design

The client must be able to submit multiple recipients in one request. The implementation should avoid holding the HTTP request open while all PDFs are generated.

### NFR-02 — Failure isolation

Individual recipient failures must be captured without terminating the entire batch unnecessarily.

### NFR-03 — Observability

The system should log job lifecycle events and unexpected failures with job and recipient identifiers. API responses must not expose stack traces or secrets.

### NFR-04 — Data consistency

Job-level counters and status must agree with the persisted recipient results. State changes should be committed consistently.

### NFR-05 — Safe file handling

Generated filenames and file paths must not allow path traversal or access to unrelated files. Only successfully generated certificates should be downloadable.

### NFR-06 — Maintainability

The API, application services, PDF generator, queue worker, database access, and storage implementation should be separated into understandable modules.

### NFR-07 — Testability

The required behavior must be covered by automated tests that can run in a repeatable development/test environment.

### NFR-08 — Explainability

The submitted code and design decisions must be understandable and modifiable by the developer.

No specific throughput, maximum batch size, uptime, or latency target has been specified. These values should not be claimed until they are explicitly decided and tested.

## 7. Technology Requirements

| Concern | Selected technology | Purpose |
|---|---|---|
| Language | Python 3.12+ | Backend implementation |
| API framework | FastAPI | REST API and OpenAPI documentation |
| Data validation | Pydantic | Request and response schemas |
| Database | PostgreSQL | Persistent relational data |
| ORM | SQLAlchemy 2.x | Database interaction |
| Migrations | Alembic | Version-controlled schema updates |
| PDF generation | ReportLab | Certificate PDF rendering |
| Background queue | Redis + RQ | Queue and execute generation jobs |
| Testing | Pytest + HTTPX | Unit and API integration tests |
| Local environment | Docker Compose | Run dependent services locally |
| File storage | Local filesystem for MVP | Persist generated PDFs |

These are the proposed project choices. The original assignment permits FastAPI, Django REST Framework, or Flask and does not mandate a particular database, PDF library, or background queue.

## 8. API Requirements

All business endpoints use the `/api/v1` prefix.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/jobs` | Create a bulk generation job |
| `GET` | `/api/v1/jobs/{job_id}` | Retrieve job status and progress |
| `GET` | `/api/v1/jobs/{job_id}/certificates` | List recipient results for a job |
| `GET` | `/api/v1/certificates/{certificate_id}/download` | Download a generated PDF |
| `GET` | `/health` | Check application health |

### 8.1 Request example

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

This is the proposed initial payload. Final field names and constraints must be defined in the API schemas.

### 8.2 Accepted-job response

The asynchronous API should return HTTP `202 Accepted` after persisting the job.

```json
{
  "job_id": "generated-uuid",
  "status": "queued",
  "total_recipients": 2,
  "completed": 0,
  "failed": 0
}
```

### 8.3 Progress response

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

The values are illustrative. The implementation must calculate them from persisted state rather than hardcode them.

### 8.4 HTTP behavior

- `202 Accepted` when a generation job has been accepted for background processing.
- `404 Not Found` for unknown job or certificate identifiers.
- Appropriate `4xx` responses for malformed request payloads.
- A successful download response only when the certificate exists and is completed.
- A consistent error response format across endpoints.

## 9. Data Requirements

### 9.1 Generation job

Each job must store:

- Unique job identifier.
- Overall status.
- Total recipient count.
- Successful count.
- Failed count.
- Creation, start, and completion timestamps.

### 9.2 Recipient/certificate result

Each recipient record must store:

- Unique certificate/result identifier.
- Parent job identifier.
- Recipient name and email when available.
- Processing status.
- Generated file key/path when successful.
- Failure message when unsuccessful.
- Creation and completion timestamps.

### 9.3 Relationship

One generation job has many recipient/certificate records.

The database is the source of truth for job progress and results. Redis is used for dispatching work, not as the sole record of the job's state.

## 10. Status Definitions

### Recipient statuses

- `pending`: waiting to be processed.
- `processing`: currently being processed.
- `completed`: PDF generated and its file reference persisted.
- `failed`: validation or generation failed.

### Job statuses

- `queued`: accepted and waiting for processing.
- `processing`: at least some work is in progress.
- `completed`: all recipients succeeded.
- `completed_with_errors`: a mixture of successful and failed results.
- `failed`: the job could not be executed as a whole, or all recipients failed according to the final documented policy.

The implementation must make final-state rules deterministic, including behavior for an empty recipient list or a job where every recipient is invalid.

## 11. Failure Handling and Recovery

- Validate each recipient independently where possible.
- Record a useful failure reason for every failed recipient.
- Continue to the next recipient after an individual generation error.
- Avoid exposing internal stack traces to clients.
- Store generated files using safe, unique file keys.
- Consider the possibility that the database transaction succeeds but queue submission fails.
- Define retry limits and behavior for worker interruptions.
- Make retries idempotent where practical to prevent uncontrolled duplicate files.
- Reconcile job counters and final status with recipient-level records.
- Handle missing files and unknown identifiers without exposing filesystem details.

## 12. Testing Requirements

At minimum, tests must cover:

- Creating a generation job.
- Input and recipient validation.
- Certificate PDF generation.
- Job status and progress calculation.
- Individual certificate failure while other recipients continue.
- Listing results.
- Retrieving/downloading generated certificates.

Recommended additional tests:

- Empty recipient lists and malformed payloads.
- Unicode and long names.
- Duplicate recipients.
- Unknown IDs and missing files.
- Concurrent jobs.
- Worker exceptions and retries.
- Consistency of status counters and final job state.

## 13. Deliverables

The project submission should include:

1. Python source code.
2. FastAPI endpoints and request/response schemas.
3. Database models and migration files.
4. Fixed certificate template and PDF-generation service.
5. Background worker and queue configuration, if using the proposed architecture.
6. Automated tests.
7. `.env.example` and `.gitignore`.
8. `README.md` with setup, run, test, and API instructions.
9. `docs/architecture.md` with architecture and design decisions.
10. Dockerfile and Docker Compose configuration for reproducible local development.
11. A working demonstration of bulk submission, progress tracking, partial failure handling, and certificate download.

## 14. Acceptance Criteria

Certix is considered ready for submission when:

- A client can submit multiple recipients in one request.
- The API returns a job identifier and initial status.
- Every recipient entry has a persisted result.
- Valid recipients receive personalized PDF certificates.
- An individual certificate failure does not stop unrelated recipients.
- Job progress and final status reflect actual recipient results.
- Successful certificates can be downloaded safely.
- Required automated tests pass.
- A fresh developer can run the project using the README.
- The implementation and its design choices can be explained and modified during an interview.

## 15. Implementation Priorities

1. Complete the architecture and API schemas.
2. Establish the FastAPI application and relational database.
3. Implement job creation and recipient persistence.
4. Implement the fixed PDF template and generation service.
5. Add background processing and failure isolation.
6. Add progress, results, and download endpoints.
7. Complete mandatory tests and reliability checks.
8. Finalize documentation and verify the submission from a clean checkout.

**Priority rule:** required assignment functionality takes precedence over optional features.
