# Certix — Testing Strategy

**Project:** Certix — Bulk Certificate Generator Backend API  
**Document location:** `.ai/testing_strategy.md`  
**Test framework:** Pytest  
**API test client:** HTTPX / FastAPI TestClient  
**Status:** Proposed test plan

This document defines how Certix will be verified during development. Tests must reflect the project specification, API contract, database design, and implementation decisions. When those documents change, update the relevant tests in the same change.

---

## 1. Testing Objectives

Testing must establish that Certix:

- Accepts a bulk generation request and persists a job.
- Validates request data and handles recipient-level failures according to the agreed contract.
- Generates personalized PDF certificates from the predefined template.
- Processes recipients independently so one failure does not unnecessarily stop the batch.
- Persists accurate job and recipient statuses.
- Reports progress and results consistently.
- Allows successful certificates to be downloaded safely.
- Handles missing records, invalid inputs, and dependency failures without leaking internal details.
- Can be installed, configured, and tested using the documented instructions.

Do not claim a test passed unless it was actually run and its result was observed.

## 2. Testing Layers

| Layer | Purpose | Typical tools |
|---|---|---|
| Unit tests | Test isolated functions and services | Pytest, mocks, temporary directories |
| API tests | Verify request validation, HTTP status codes, and response schemas | FastAPI TestClient or HTTPX |
| Database integration tests | Verify models, constraints, migrations, and persistence | PostgreSQL test database, SQLAlchemy |
| Worker integration tests | Verify background processing, status transitions, and failure isolation | RQ test configuration or controlled worker tests |
| End-to-end tests | Verify submission through PDF retrieval | FastAPI client, test database, test worker, temporary storage |
| Manual smoke tests | Verify the documented local workflow | Swagger UI, curl, or Postman |

Use mocks for isolated unit tests, but do not replace all database and worker integration tests with mocks. Important persistence and transaction behavior must be tested against a real test database where practical.

---

## 3. Test Environment and Fixtures

### Environment rules

- Use a dedicated test database, never a developer's normal database.
- Use a temporary directory for generated PDFs.
- Do not use production credentials or real recipient data.
- Keep test configuration separate from `.env` used for local development.
- Tests should clean up temporary files and records.
- External Redis usage should be isolated from a developer's normal queue.
- Prefer deterministic tests that do not depend on timing, network access, or external services.

### Suggested fixtures

Create reusable fixtures in `tests/conftest.py` as needed:

- `client`: FastAPI test client.
- `db_session`: isolated database session or transaction.
- `test_job`: a persisted generation job.
- `sample_request`: valid request with two recipients.
- `temp_storage`: temporary certificate storage directory.
- `settings_override`: test-only configuration.
- `mock_pdf_failure`: controlled generator failure for one recipient.
- `worker_runner`: a way to execute queued work deterministically in tests.

Use a real PostgreSQL test database for PostgreSQL-specific constraints and migration checks. SQLite may be used for simple isolated tests only if the differences do not invalidate the behavior being tested.

---

## 4. Test Naming and Organization

Use descriptive names that state the behavior being verified.

```text
tests/
├── conftest.py
├── test_health.py
├── test_jobs.py
├── test_validation.py
├── test_database.py
├── test_generation.py
├── test_worker.py
├── test_progress.py
├── test_failures.py
├── test_downloads.py
└── test_end_to_end.py
```

Example test names:

- `test_create_job_returns_202_and_job_id`
- `test_create_job_persists_one_result_per_recipient`
- `test_empty_recipient_list_is_rejected`
- `test_invalid_recipient_is_recorded_as_failed`
- `test_pdf_contains_recipient_name`
- `test_one_generation_failure_does_not_stop_other_recipients`
- `test_progress_matches_terminal_recipient_counts`
- `test_pending_certificate_cannot_be_downloaded`
- `test_download_rejects_path_traversal`
- `test_unknown_job_returns_404`

The exact file layout may evolve, but tests should remain discoverable and focused.

---

## 5. Required Test Matrix

### 5.1 Health check

| Scenario | Expected result |
|---|---|
| API process is available | `GET /health` returns `200` |
| Response is valid | Response matches the documented health schema |

### 5.2 Job creation

| Scenario | Expected result |
|---|---|
| Valid request with multiple recipients | `202`; job ID returned |
| Job accepted | Job and recipient records are persisted |
| Two recipients submitted | Exactly two recipient/result records are created |
| Missing `event_name` | Request rejected with validation error |
| Invalid `completion_date` | Request rejected with validation error |
| Invalid email | Handled according to the documented recipient-level validation policy |
| Empty recipient array | Request rejected; no job created |
| Whitespace-only required field | Rejected or recorded as a recipient failure according to field location and contract |
| Malformed JSON | Consistent `4xx` error response |
| Database write failure | No false accepted response; transaction rolls back where applicable |
| Queue dispatch failure after commit | Failure is surfaced or recoverable; job must not remain stuck indefinitely |

### 5.3 Input validation

Test:

- Required fields are present.
- String values are trimmed where specified.
- Empty names and event names are rejected.
- Dates are valid calendar dates and use the documented format.
- Email validation follows the selected schema/library behavior.
- Unicode recipient names are accepted.
- Maximum field lengths are enforced.
- Top-level payload errors are distinct from recipient-level validation errors.
- Duplicate recipients follow the documented policy.
- Invalid entries retain enough information to identify the failure without unsafe or excessive data storage.

### 5.4 Certificate generation

| Scenario | Expected result |
|---|---|
| Valid recipient | A readable PDF is created |
| Recipient-specific data | Correct recipient and event details are rendered |
| Unicode name | PDF generation succeeds with a compatible font |
| Long name | Text remains legible and within the intended layout |
| Unsafe characters in name | File path remains safe; name is treated as content |
| Generator raises an exception | Controlled failure is returned to the worker |
| Storage write fails | Recipient is marked failed; no false success is reported |
| Existing output key during retry | Retry behavior is deterministic and does not corrupt another certificate |

Do not rely only on file existence. At least one test should verify that the output is a valid PDF, and content/layout checks should verify the important personalized fields.

### 5.5 Background worker and failure isolation

| Scenario | Expected result |
|---|---|
| Job is queued | Worker can retrieve and process it |
| All recipients succeed | Job becomes `completed` |
| One recipient fails, others succeed | Remaining recipients continue; job becomes `completed_with_errors` |
| All recipients fail | Final status follows the documented all-failed policy |
| Invalid recipient record | It remains failed and does not block valid entries |
| Unexpected error for one recipient | Error is logged and recipient is marked failed where safe |
| Duplicate queue delivery | Duplicate processing is prevented or safely idempotent |
| Worker stops during processing | Recovery behavior follows the documented policy |
| Database update fails after PDF creation | No false completed status; reconciliation or cleanup behavior is defined |
| Queue enqueue fails | Recovery or explicit dispatch-failure handling prevents a permanently stuck job |

Worker tests should verify persisted outcomes, not just that a function was called.

### 5.6 Job status and progress

Verify:

- Unknown job IDs return `404`.
- Status values belong to the documented set.
- `processed = completed + failed`.
- Counts agree with recipient records.
- Progress is between `0` and `100`.
- Progress is `0` before any recipient reaches a terminal state.
- Progress reaches `100` when all recipients reach terminal states.
- Final job status agrees with the individual recipient outcomes.
- `started_at` and `finished_at` are populated at the appropriate transitions.
- Concurrent processing does not produce negative, inflated, or inconsistent counts.

### 5.7 Result listing

Verify:

- Only results for the requested job are returned.
- Both successful and failed recipient results are included.
- Successful results have a certificate ID and download URL.
- Failed results have a useful error code/message and no download URL.
- `limit` and `offset` behave as documented.
- Invalid pagination parameters return a validation error.
- Unknown jobs return `404`.
- Response fields match the API contract.

### 5.8 Certificate downloads

| Scenario | Expected result |
|---|---|
| Completed certificate with existing file | `200`, `application/pdf`, valid PDF body |
| Pending or processing certificate | `409` or the exact documented not-ready behavior |
| Failed certificate | Not downloadable |
| Unknown certificate ID | `404` |
| Missing output file | Safe `404`; no filesystem details exposed |
| Path traversal attempt | Rejected; no file outside storage root is returned |
| Filename contains special characters | Response filename remains safe |
| File read error | Controlled error; no stack trace in response |

### 5.9 Database and migration tests

Verify:

- Foreign-key relationship between jobs and certificates.
- Valid and invalid status values are handled according to model/database constraints.
- Check constraints prevent negative counts.
- Job creation rolls back atomically when record creation fails.
- Migrations create the expected schema on an empty database.
- Migrations can be applied from the documented starting state.
- Counter values, if stored, remain consistent with child records.
- Database sessions are properly closed or rolled back after failures.

---

## 6. End-to-End Acceptance Scenarios

### Scenario A — All recipients succeed

1. Submit a job with two valid recipients.
2. Verify `202 Accepted` and a job ID.
3. Run the worker.
4. Poll the job endpoint.
5. Verify the job is `completed`, with two completed and zero failed.
6. List results and verify both certificates have download URLs.
7. Download both PDFs and verify their content.

**Pass condition:** every submitted recipient has a successful result and a retrievable PDF.

### Scenario B — One recipient fails

1. Submit a job with three recipients.
2. Configure the test generator to fail for one recipient only.
3. Run the worker.
4. Verify the other two recipients are completed.
5. Verify the failed recipient contains an error code/message.
6. Verify the job is `completed_with_errors`.
7. Download the two successful PDFs.
8. Verify the failed certificate cannot be downloaded.

**Pass condition:** the failure is isolated, results are accurate, and successful files remain retrievable.

### Scenario C — Invalid recipient

1. Submit a batch containing valid recipients and a recipient with invalid data.
2. Verify the agreed validation policy is followed.
3. Verify the invalid entry is identifiable in the results.
4. Verify valid recipients still complete.
5. Verify counts and final status match the results.

**Pass condition:** behavior matches the API contract and invalid data does not silently disappear.

### Scenario D — Missing file

1. Generate a certificate successfully.
2. Remove the output file in the test environment.
3. Request the download.
4. Verify a safe error response is returned.
5. Verify no absolute filesystem path or stack trace is exposed.

**Pass condition:** the API handles inconsistent storage safely.

### Scenario E — Clean setup

1. Start from a fresh checkout.
2. Create the environment and install dependencies.
3. Configure environment variables.
4. Start PostgreSQL and Redis.
5. Run database migrations.
6. Start the API and worker.
7. Run the test suite.
8. Submit a sample job and download a certificate.

**Pass condition:** all steps work using the README without undocumented local setup.

---

## 7. Test Commands

The final commands must match the selected package manager and repository configuration. A typical Pytest workflow is:

```bash
# Run all tests
pytest

# Run a focused test module
pytest tests/test_jobs.py

# Show individual test names and outcomes
pytest -v

# Stop after the first failure
pytest -x

# Optional coverage report, if pytest-cov is configured
pytest --cov=app --cov-report=term-missing
```

Do not introduce a coverage threshold unless the team chooses one. Coverage percentage is a useful signal, but it does not prove that critical behavior is tested.

---

## 8. Continuous Integration (Optional but Recommended)

A CI workflow may:

1. Install the supported Python version and dependencies.
2. Start PostgreSQL and Redis services.
3. Configure test environment variables.
4. Run migrations against a clean test database.
5. Run formatting and lint checks if configured.
6. Run the automated test suite.
7. Report failures and test results.

CI is useful, but it must not delay implementation of the assignment's mandatory functionality.

---

## 9. Definition of Done for Testing

Testing is complete for submission when:

- [ ] All mandatory assignment test categories are covered.
- [ ] Job creation and persistence are verified.
- [ ] Request and recipient validation are verified.
- [ ] PDF generation is verified.
- [ ] Job progress and final status are verified.
- [ ] Individual certificate failure isolation is verified.
- [ ] Certificate retrieval and download behavior is verified.
- [ ] Important database constraints and migrations are tested.
- [ ] The full test suite passes in the documented environment.
- [ ] Test results are reported honestly and reproducibly.
- [ ] A clean-clone smoke test succeeds.

**Priority rule:** test required functionality and failure paths before adding optional features.
