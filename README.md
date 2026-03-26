
**Candidate:** Amrutha Varshini  
**Framework:** Python + Pytest  
**Base URL:** https://qa-testing-navy.vercel.app

---

## Testing Strategy

### Framework Choice
Python with Pytest was chosen for its clean fixture system, readable assertions, and easy repeatability.

### Handling the Async Nature
The caption processing job is asynchronous. After triggering `/process-captions`, the suite polls `GET /api/videos/{id}` in a loop with a 3-second interval and a 30-second deadline, checking for `status: "completed"` before proceeding to fetch captions.

### Handling Token Expiry (5 seconds)
Tokens expire in 5 seconds, making it impossible to reuse a token across multiple steps. The suite uses a `fresh_token()` helper that re-authenticates before every API call. However, re-authentication with the same Candidate ID triggers a `StateCollision` error (Bug #3), so a **unique Candidate ID is generated per test run** using `uuid4`. This ensures full repeatability — the suite passes cleanly on every run.

### Test Structure
Tests are grouped into 5 classes:
- `TestAuth` — authentication, token lifecycle, session collision
- `TestVideoCreation` — create video, field validation, auth enforcement
- `TestCaptionProcessing` — full lifecycle, duplicate trigger, invalid IDs
- `TestDeletion` — delete happy path, idempotency, phantom deletes
- `TestIsolation` — cross-candidate data access

---

## Bugs Found (10 Total)

| # | Endpoint | Bug | Expected | Actual |
|---|----------|-----|----------|--------|
| 1 | `POST /api/videos` | Title field is ignored | Title matches request | Always returns `"New Video"` |
| 2 | `GET /api/videos` | Token expiry inconsistent | Expire after 5s always | Sometimes valid after 6s |
| 3 | `POST /api/auth` | Cannot re-authenticate with same ID | Allow re-auth | Returns `409 StateCollision` |
| 4 | `POST /api/auth` | Wrong success status code | `200 OK` | Returns `201 Created` |
| 5 | `POST /api/videos` | No authentication required | `401` without token | Creates video without any token |
| 6 | `POST /api/videos` | Accepts empty request body | `400 Bad Request` | Creates video with no fields |
| 7 | `POST /api/videos/{id}/process-captions` | Wrong status code | `200 OK` | Returns `202 Accepted` with no async callback |
| 8 | `POST /api/videos/{id}/process-captions` | Can trigger captions twice | `400` or `409` | Allows duplicate processing |
| 9 | `GET /api/captions?videoId={id}` | No 404 for invalid video | `404 Not Found` | Returns `200 []` silently |
| 10 | `DELETE /api/videos/{id}` | Phantom delete succeeds silently | `404 Not Found` | Returns `204` for non-existent/already-deleted videos |

---


```bash
pip install pytest requests
```


```bash
pytest test_pipeline.py -v
```

The suite is fully repeatable — each test generates a unique `X-Candidate-ID` so there are no session conflicts between runs.