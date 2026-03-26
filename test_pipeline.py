import pytest
import requests
import time
import uuid

BASE_URL = "https://qa-testing-navy.vercel.app"


@pytest.fixture
def candidate_id():
    """Each test gets its own unique candidate ID — prevents StateCollision."""
    return f"amrutha-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def token(candidate_id):
    """Get a fresh token for a given candidate ID."""
    return get_token(candidate_id)


def get_token(candidate_id):
    res = requests.post(
        f"{BASE_URL}/api/auth",
        json={"username": "test", "password": "test"},
        headers=make_headers(candidate_id)
    )
    assert res.status_code in [200, 201], f"Auth failed: {res.text}"
    t = res.json().get("token")
    assert t, "No token returned"
    return t


def make_headers(candidate_id, token=None):
    h = {
        "Content-Type": "application/json",
        "X-Candidate-ID": candidate_id
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def create_video(candidate_id, token, title="My Test Video"):
    return requests.post(
        f"{BASE_URL}/api/videos",
        json={"title": title, "url": "https://example.com/video.mp4"},
        headers=make_headers(candidate_id, token)
    )


def delete_video(candidate_id, video_id, token):
    requests.delete(
        f"{BASE_URL}/api/videos/{video_id}",
        headers=make_headers(candidate_id, token)
    )


class TestAuth:

    def test_auth_returns_token(self, candidate_id):
        """Happy path — valid auth returns a token and expiresAt."""
        res = requests.post(
            f"{BASE_URL}/api/auth",
            json={"username": "test", "password": "test"},
            headers=make_headers(candidate_id)
        )
        assert res.status_code in [200, 201], f"Auth failed: {res.text}"
        if res.status_code == 201:
            pytest.fail(
                "Bug #4 Confirmed: POST /api/auth returns 201 (Created) instead of 200 (OK). "
                "Auth is not creating a resource, it should return 200."
            )
        data = res.json()
        assert "token" in data
        assert "expiresAt" in data

    def test_auth_without_candidate_id(self):
        """Bug Hunt — missing X-Candidate-ID should be rejected."""
        res = requests.post(
            f"{BASE_URL}/api/auth",
            json={"username": "test", "password": "test"},
            headers={"Content-Type": "application/json"}
        )
        assert res.status_code in [400, 401], (
            f"Bug: API accepted request with no X-Candidate-ID. Got {res.status_code}"
        )

    def test_token_expires_in_5_seconds(self, candidate_id, token):
        """Bug #2 — Token expires in only 5 seconds, too short for real workflows.
           Note: expiry appears inconsistent — another bug in itself."""
        time.sleep(6)
        res = requests.get(
            f"{BASE_URL}/api/videos",
            headers=make_headers(candidate_id, token)
        )
        if res.status_code == 200:
            pytest.fail(
                "Bug #2 Confirmed (Inconsistent): Token should expire after 5 seconds "
                "per the API spec, but request succeeded after 6 seconds. "
                "Token expiry is not being enforced consistently."
            )
        assert res.status_code == 401
        assert "TokenExpired" in res.json().get("error", "")

    def test_state_collision_on_duplicate_auth(self, candidate_id, token):
        """Bug #3 — Same Candidate ID cannot have two active sessions."""
        res = requests.post(
            f"{BASE_URL}/api/auth",
            json={"username": "test", "password": "test"},
            headers=make_headers(candidate_id)
        )
        assert res.status_code == 409, (
            f"Bug #3 Confirmed: StateCollision — re-authenticating with same ID should return 409. Got {res.status_code}"
        )
        assert res.json().get("error") == "StateCollision"

    def test_auth_without_body(self, candidate_id):
        """Bug Hunt — auth with empty body should not issue a token."""
        res = requests.post(
            f"{BASE_URL}/api/auth",
            json={},
            headers=make_headers(candidate_id)
        )
        assert res.status_code != 200 or "token" not in res.json(), (
            "Bug: API issued a token with empty credentials"
        )


class TestVideoCreation:

    def test_create_video_returns_id(self, candidate_id, token):
        """Happy path — video creation returns an ID and correct fields."""
        res = create_video(candidate_id, token)
        assert res.status_code in [200, 201]
        data = res.json()
        assert "id" in data
        assert "status" in data
        assert data["status"] == "pending"
        delete_video(candidate_id, data["id"], token)

    def test_title_is_persisted_correctly(self, candidate_id, token):
        """Bug #1 — Title sent in request should match title stored."""
        res = create_video(candidate_id, token, title="My Unique Title 123")
        data = res.json()
        assert data.get("title") == "My Unique Title 123", (
            f"Bug #1 Confirmed: Title not persisted. Sent 'My Unique Title 123', got '{data.get('title')}'"
        )
        delete_video(candidate_id, data["id"], token)

    def test_create_video_without_auth(self, candidate_id):
        """Bug #5 — Creating a video without a token should be rejected."""
        res = requests.post(
            f"{BASE_URL}/api/videos",
            json={"title": "No Auth Video",
                  "url": "https://example.com/video.mp4"},
            headers=make_headers(candidate_id)  # No token
        )
        assert res.status_code in [401, 403], (
            f"Bug #5 Confirmed: API allowed video creation without auth token. "
            f"Got {res.status_code}: {res.text}"
        )

    def test_create_video_missing_fields(self, candidate_id, token):
        """Bug #6 — Creating a video with empty body should return 400."""
        res = requests.post(
            f"{BASE_URL}/api/videos",
            json={},
            headers=make_headers(candidate_id, token)
        )
        assert res.status_code == 400, (
            f"Bug #6 Confirmed: API accepted video creation with empty body. "
            f"Got {res.status_code}: {res.text}"
        )


class TestCaptionProcessing:

    def test_full_lifecycle(self, candidate_id, token):
        """Happy path — full end-to-end lifecycle with polling."""
        # Create
        res = create_video(candidate_id, token, title="Lifecycle Video")
        assert res.status_code in [200, 201]
        video_id = res.json()["id"]

        # Trigger captions — Bug #7: returns 202 instead of 200
        res = requests.post(
            f"{BASE_URL}/api/videos/{video_id}/process-captions",
            headers=make_headers(candidate_id, token)
        )
        assert res.status_code in [
            200, 202], f"Unexpected status: {res.status_code}"
        if res.status_code == 202:
            pytest.fail(
                "Bug #7 Confirmed: POST /api/videos/{id}/process-captions returns 202 "
                "but there is no async callback or polling mechanism documented. "
                "Should return 200 with processing confirmation."
            )
        assert "Processing started" in res.json().get("message", "")

        # Poll for completion
        completed = False
        deadline = time.time() + 30
        while time.time() < deadline:
            res = requests.get(
                f"{BASE_URL}/api/videos/{video_id}",
                headers=make_headers(candidate_id, token)
            )
            if res.status_code == 401:
                pytest.skip(
                    "Token expired during polling (Bug #2 + Bug #3 interaction)")
            assert res.status_code == 200
            if res.json().get("status") == "completed":
                completed = True
                break
            time.sleep(3)

        assert completed, "Bug: Video never reached 'completed' status within 30 seconds"

        res = requests.get(
            f"{BASE_URL}/api/captions?videoId={video_id}",
            headers=make_headers(candidate_id, token)
        )
        assert res.status_code == 200

        delete_video(candidate_id, video_id, token)

    def test_process_captions_twice(self, candidate_id, token):
        """Bug #8 — Triggering captions twice on same video should be rejected."""
        res = create_video(candidate_id, token)
        video_id = res.json()["id"]

        requests.post(
            f"{BASE_URL}/api/videos/{video_id}/process-captions",
            headers=make_headers(candidate_id, token)
        )
        res = requests.post(
            f"{BASE_URL}/api/videos/{video_id}/process-captions",
            headers=make_headers(candidate_id, token)
        )
        assert res.status_code in [400, 409], (
            f"Bug #8 Confirmed: API allowed triggering captions twice on same video. "
            f"Got {res.status_code}: {res.text}"
        )
        delete_video(candidate_id, video_id, token)

    def test_captions_for_nonexistent_video(self, candidate_id, token):
        """Bug #9 — Fetching captions for a fake video ID should return 404."""
        res = requests.get(
            f"{BASE_URL}/api/captions?videoId=fake-id-99999",
            headers=make_headers(candidate_id, token)
        )
        assert res.status_code == 404, (
            f"Bug #9 Confirmed: API returned {res.status_code} for non-existent video captions. "
            f"Got: {res.text} — should return 404."
        )


class TestDeletion:

    def test_delete_video(self, candidate_id, token):
        """Happy path — delete a video successfully."""
        res = create_video(candidate_id, token)
        video_id = res.json()["id"]
        res = requests.delete(
            f"{BASE_URL}/api/videos/{video_id}",
            headers=make_headers(candidate_id, token)
        )
        assert res.status_code in [200, 204]

    def test_delete_nonexistent_video(self, candidate_id, token):
        """Bug #10 — Deleting a non-existent video should return 404, not 204."""
        res = requests.delete(
            f"{BASE_URL}/api/videos/nonexistent-fake-id-xyz",
            headers=make_headers(candidate_id, token)
        )
        assert res.status_code == 404, (
            f"Bug #10 Confirmed: Deleting non-existent video returned {res.status_code} "
            f"instead of 404. Silent success on phantom delete is dangerous."
        )

    def test_delete_same_video_twice(self, candidate_id, token):
        """Bug #10 (continued) — Second delete of same video should return 404."""
        res = create_video(candidate_id, token)
        video_id = res.json()["id"]

        requests.delete(
            f"{BASE_URL}/api/videos/{video_id}",
            headers=make_headers(candidate_id, token)
        )
        res = requests.delete(
            f"{BASE_URL}/api/videos/{video_id}",
            headers=make_headers(candidate_id, token)
        )
        assert res.status_code == 404, (
            f"Bug #10 Confirmed: Second delete returned {res.status_code} instead of 404. "
            f"API silently succeeds on already-deleted resources."
        )

    def test_get_deleted_video(self, candidate_id, token):
        """Happy path verification — fetching a deleted video should return 404."""
        res = create_video(candidate_id, token)
        video_id = res.json()["id"]

        requests.delete(
            f"{BASE_URL}/api/videos/{video_id}",
            headers=make_headers(candidate_id, token)
        )
        res = requests.get(
            f"{BASE_URL}/api/videos/{video_id}",
            headers=make_headers(candidate_id, token)
        )
        assert res.status_code == 404, (
            f"Bug: Deleted video still accessible. Got {res.status_code}"
        )


class TestIsolation:

    def test_cannot_access_other_candidates_video(self):
        """Bug Hunt — Candidate B should not access Candidate A's video."""
        id_a = f"candidate-a-{uuid.uuid4().hex[:8]}"
        id_b = f"candidate-b-{uuid.uuid4().hex[:8]}"

        token_a = get_token(id_a)
        res = requests.post(
            f"{BASE_URL}/api/videos",
            json={"title": "Private Video", "url": "https://example.com/a.mp4"},
            headers=make_headers(id_a, token_a)
        )
        video_id = res.json()["id"]

        token_b = get_token(id_b)
        res = requests.get(
            f"{BASE_URL}/api/videos/{video_id}",
            headers=make_headers(id_b, token_b)
        )
        assert res.status_code in [403, 404], (
            f"Bug: Candidate B accessed Candidate A's video! Got {res.status_code}: {res.text}"
        )

        delete_video(id_a, video_id, token_a)
