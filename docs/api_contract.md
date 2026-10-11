# Certix API Contract

**Project:** Certix — Bulk Certificate Generator  
**API version:** `v1`  
**Base path:** `/api/v1`  
**Status:** Proposed contract for implementation

This document defines the initial HTTP contract for Certix. The schemas and examples below are implementation decisions based on the project specification; they should be kept in sync with the FastAPI/Pydantic models.

---

## 1. API Conventions

- Use JSON for request and response bodies unless an endpoint returns a PDF file.
- Use UUIDs for job and certificate identifiers.
- Use ISO 8601 dates and timestamps.
- Use the `/api/v1` prefix for business endpoints.
- Return a consistent JSON error shape for API errors.
- Persist a job and its recipient records before acknowledging that the job has been accepted.
- Bulk generation is asynchronous. A successful submission returns `202 Accepted`; clients poll the job status endpoint for progress.
- Do not return filesystem paths to clients. Return certificate IDs and download endpoints instead.
- Do not expose stack traces, secrets, database details, or internal filesystem paths in error responses.

### Content types

- JSON requests: `Content-Type: application/json`
- PDF downloads: `Content-Type: application/pdf`

---

## 2. Endpoint Summary

| Method | Endpoint | Purpose | Success response |
|---|---|---|---|
| `GET` | `/health` | Health check | `200 OK` |
| `POST` | `/api/v1/jobs` | Create bulk generation job | `202 Accepted` |
| `GET` | `/api/v1/jobs/{job_id}` | Get job status and progress | `200 OK` |
| `GET` | `/api/v1/jobs/{job_id}/certificates` | List recipient results for a job | `200 OK` |
| `GET` | `/api/v1/certificates/{certificate_id}/download` | Download a generated certificate | `200 OK` with PDF |

---

## 3. Shared Data Models

### 3.1 Recipient input

| Field | Type | Required | Rules |
|---|---|---:|---|
| `name` | string | Yes | Trim whitespace; must not be empty |
| `email` | string | Yes | Must be a valid email address |

Names should support Unicode characters. The API should reject missing or empty required values. A name that is too long should be handled according to a documented maximum length enforced by the schema and database.

### 3.2 Job creation input

| Field | Type | Required | Rules |
|---|---|---:|---|
| `event_name` | string | Yes | Non-empty after trimming |
| `completion_date` | string (`YYYY-MM-DD`) | Yes | Valid calendar date |
| `recipients` | array of recipient input | Yes | Must contain at least one entry |

The initial contract uses `event_name` and `completion_date` as shared certificate fields. Additional fields, such as issuer name or certificate ID display text, should only be added if the agreed certificate template requires them.

### 3.3 Status enums

**Job status**

- `queued`
- `processing`
- `completed`
- `completed_with_errors`
- `failed`

**Recipient/certificate status**

- `pending`
- `processing`
- `completed`
- `failed`

Final status rules must be implemented consistently:

- `completed`: all recipient entries completed successfully.
- `completed_with_errors`: at least one recipient succeeded and at least one failed.
- `failed`: the job could not run as a whole, or all recipient entries failed under the project's documented policy.

An empty recipient list is rejected at request validation, so it does not create a job.

---

## 4. `GET /health`

Checks whether the API process is responding.

### Success — `200 OK`

```json
{
  "status": "ok"
}
```

This endpoint is a basic process health check. If database/Redis dependency health checks are added, document their semantics separately.

---

## 5. `POST /api/v1/jobs`

Creates a bulk certificate generation job.

### Request

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

### Accepted response — `202 Accepted`

```json
{
  "job_id": "d5b1a9c7-6d8b-4d10-8d35-3d3a1f3d9a20",
  "status": "queued",
  "total_recipients": 2,
  "completed": 0,
  "failed": 0,
  "status_url": "/api/v1/jobs/d5b1a9c7-6d8b-4d10-8d35-3d3a1f3d9a20"
}
```

The UUID is illustrative. The server generates the actual ID.

### Behavior

1. Validate the top-level payload and recipient entries.
2. Create a job record and a recipient/result record for each submitted entry.
3. Commit the records to the database.
4. Enqueue the job for background processing.
5. Return `202 Accepted` with the job ID and status URL.

The implementation must address the gap between database commit and queue enqueue. If enqueueing fails, it must not silently leave a job permanently queued; implement a recovery strategy or mark/report the dispatch failure clearly.

### Errors

- `422 Unprocessable Entity`: malformed JSON structure, missing required fields, invalid email/date, or an empty recipient array.
- `503 Service Unavailable`: the service cannot accept a job because a required dependency is unavailable.
- `500 Internal Server Error`: unexpected failure, with no internal details leaked to the client.

**Validation policy:** malformed top-level requests are rejected as a whole. For recipient-level validation failures that can be represented in the input model, the intended product behavior is to retain a per-recipient failed result and continue processing other entries. If Pydantic validation rejects a recipient before job creation, that recipient cannot be recorded in the job. The implementation must choose and test one consistent approach. Recommended approach for explicit partial validation: accept raw recipient entries at the batch boundary, validate each recipient independently, and persist invalid entries as failed results.

---

## 6. `GET /api/v1/jobs/{job_id}`

Returns job status and aggregate progress.

### Success — `200 OK`

```json
{
  "job_id": "d5b1a9c7-6d8b-4d10-8d35-3d3a1f3d9a20",
  "status": "processing",
  "total_recipients": 100,
  "processed": 45,
  "completed": 42,
  "failed": 3,
  "progress_percentage": 45,
  "created_at": "2026-10-10T09:00:00Z",
  "started_at": "2026-10-10T09:00:02Z",
  "finished_at": null
}
```

### Field definitions

| Field | Type | Meaning |
|---|---|---|
| `job_id` | UUID string | Job identifier |
| `status` | string | Current job status |
| `total_recipients` | integer | Number of submitted recipient entries |
| `processed` | integer | Number of entries in a terminal state (`completed` or `failed`) |
| `completed` | integer | Number of successful certificates |
| `failed` | integer | Number of failed recipient entries |
| `progress_percentage` | number | `processed / total_recipients * 100`, rounded according to implementation policy |
| `created_at` | timestamp | Job creation time |
| `started_at` | timestamp or `null` | First processing time |
| `finished_at` | timestamp or `null` | Final completion time |

`processed` must equal `completed + failed`. While a job is running, `processed` may be less than `total_recipients`. For a completed job, `processed` must equal `total_recipients`.

### Errors

- `404 Not Found`: no job exists with the supplied ID.
- `422 Unprocessable Entity`: path parameter is not a valid UUID.

---

## 7. `GET /api/v1/jobs/{job_id}/certificates`

Lists recipient-level results for a job, including failures.

### Query parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---:|---|
| `limit` | integer | No | `50` | Maximum records returned; proposed range `1–100` |
| `offset` | integer | No | `0` | Number of records to skip |

Pagination is included to keep responses manageable for large batches.

### Success — `200 OK`

```json
{
  "job_id": "d5b1a9c7-6d8b-4d10-8d35-3d3a1f3d9a20",
  "total": 2,
  "limit": 50,
  "offset": 0,
  "results": [
    {
      "certificate_id": "ab67a4e1-9c8e-4b11-9a5a-c9b2c2a8a101",
      "recipient_name": "Arun Kumar",
      "recipient_email": "arun@example.com",
      "status": "completed",
      "download_url": "/api/v1/certificates/ab67a4e1-9c8e-4b11-9a5a-c9b2c2a8a101/download",
      "error": null
    },
    {
      "certificate_id": "e3a8e1e0-7a77-4f28-96b1-4d1e8b7f2b02",
      "recipient_name": "Priya Sharma",
      "recipient_email": "priya@example.com",
      "status": "failed",
      "download_url": null,
      "error": {
        "code": "CERTIFICATE_GENERATION_FAILED",
        "message": "The certificate could not be generated."
      }
    }
  ]
}
```

IDs and failure details are illustrative. The error message must be useful but must not reveal sensitive internal details.

### Errors

- `404 Not Found`: job does not exist.
- `422 Unprocessable Entity`: invalid pagination parameters or malformed UUID.

---

## 8. `GET /api/v1/certificates/{certificate_id}/download`

Downloads a successfully generated certificate PDF.

### Success — `200 OK`

- `Content-Type: application/pdf`
- Response body: PDF bytes.
- `Content-Disposition`: attachment with a safe filename, such as `certificate-<certificate_id>.pdf`.

### Errors

- `404 Not Found`: certificate ID does not exist, or the associated output file is unavailable.
- `409 Conflict`: certificate exists but has not completed generation.
- `422 Unprocessable Entity`: malformed certificate UUID.

Do not accept a filesystem path from the client. Resolve the file through the certificate record and configured storage root. Ensure the resolved path remains inside the permitted storage directory.

---

## 9. Common Error Response

Use a consistent response shape for API errors.

```json
{
  "error": {
    "code": "JOB_NOT_FOUND",
    "message": "No generation job was found for the supplied ID.",
    "details": null
  }
}
```

Recommended error codes include:

| HTTP status | Code | Meaning |
|---|---|---|
| `422` | `VALIDATION_ERROR` | Request or parameter validation failed |
| `404` | `JOB_NOT_FOUND` | Job does not exist |
| `404` | `CERTIFICATE_NOT_FOUND` | Certificate does not exist |
| `409` | `CERTIFICATE_NOT_READY` | Certificate generation is not complete |
| `503` | `SERVICE_UNAVAILABLE` | Required dependency unavailable |
| `500` | `INTERNAL_ERROR` | Unexpected server failure |

For validation errors, `details` may contain field-level issues. Never include secrets, raw stack traces, or sensitive infrastructure details.

---

## 10. Processing and Consistency Rules

1. A job is acknowledged only after its job and recipient records are persisted.
2. The worker processes each recipient independently.
3. Each recipient transitions from `pending` to `processing`, then to `completed` or `failed`.
4. A successful recipient is marked `completed` only after the PDF has been generated and its storage reference has been persisted.
5. A recipient failure is recorded and does not stop unrelated recipients.
6. `processed = completed + failed`.
7. Job counters and final status must match the recipient records.
8. A job reaches a terminal state only when all recipient records are terminal, unless the whole job has failed before processing can proceed.
9. Retries must not create uncontrolled duplicate records or files.
10. If queue dispatch fails after the database commit, a documented recovery mechanism must ensure the job does not remain stuck indefinitely.

---

## 11. API Acceptance Tests

The following behaviors must be tested:

- Valid bulk request returns `202` and a job ID.
- Missing fields, invalid date/email, and empty recipient list are handled according to the contract.
- Job status returns accurate counters and progress.
- Unknown job IDs return `404`.
- Results include both successful and failed recipients.
- One recipient's generation failure does not stop other recipients.
- A completed certificate can be downloaded as a PDF.
- A pending or processing certificate cannot be downloaded as a successful file.
- Unknown certificate IDs and missing output files are handled safely.
- Pagination respects `limit` and `offset`.
- Final job status and counts agree with persisted recipient records.

---

## 12. Contract Decisions to Keep in Sync

When implementing the API, keep these artifacts synchronized:

- Pydantic schemas in `app/schemas/`.
- Route behavior in `app/api/routes/`.
- Status enums and database models.
- OpenAPI documentation generated by FastAPI.
- Automated tests.
- Examples in `README.md`.

If the implementation changes the request fields, status meanings, or response shapes, update this contract and the tests in the same change.
