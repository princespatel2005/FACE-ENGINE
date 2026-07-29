"""End-to-end backend tests for Smart AI Face Recognition.

Covers auth, health, users CRUD, enrollment, single/multi recognition,
attendance, recognition history, unknowns, dashboard stats, and 401 checks.

Note: Interdependent tests (create → enroll → recognize → attendance) are
kept in a single class TestUserLifecycle so pytest-xdist `loadscope` pins
them to one worker (loadscope groups by class for test methods).
"""
import time

import pytest
import requests


# ---------------- Health ----------------
class TestHealth:
    def test_engine_ready(self, api_client, base_url):
        r = api_client.get(f"{base_url}/api/health/engine", timeout=15)
        assert r.status_code == 200
        data = r.json()
        if not data.get("ready"):
            time.sleep(5)
            data = api_client.get(f"{base_url}/api/health/engine", timeout=15).json()
        assert data["ready"] is True
        assert data["model"] == "buffalo_l"

    def test_root(self, api_client, base_url):
        r = api_client.get(f"{base_url}/api/", timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True


# ---------------- Auth ----------------
class TestAuth:
    def test_login_success(self, api_client, base_url):
        r = api_client.post(f"{base_url}/api/auth/login",
                            json={"email": "admin@example.com", "password": "admin123"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert data["user"]["email"] == "admin@example.com"
        assert data["user"]["role"] == "admin"
        # httponly cookie should be set
        assert "access_token" in r.cookies

    def test_login_invalid(self, api_client, base_url):
        r = api_client.post(f"{base_url}/api/auth/login",
                            json={"email": "admin@example.com", "password": "wrong"}, timeout=15)
        assert r.status_code == 401

    def test_me_with_bearer(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == "admin@example.com"

    def test_logout(self, authed_client, base_url):
        r = authed_client.post(f"{base_url}/api/auth/logout", timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True


# ---------------- Auth guards ----------------
class TestAuthGuards:
    """Endpoints that require auth should reject unauthenticated requests."""
    ENDPOINTS = [
        ("GET", "/api/auth/me"),
        ("GET", "/api/users"),
        ("POST", "/api/users"),
        ("POST", "/api/recognize"),
        ("POST", "/api/recognize/multi"),
        ("GET", "/api/attendance"),
        ("GET", "/api/recognition-history"),
        ("GET", "/api/unknowns"),
        ("GET", "/api/dashboard/stats"),
    ]

    @pytest.mark.parametrize("method,path", ENDPOINTS)
    def test_requires_auth(self, method, path, base_url):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        if method == "GET":
            r = s.get(f"{base_url}{path}", timeout=15)
        else:
            r = s.post(f"{base_url}{path}", json={}, timeout=15)
        assert r.status_code == 401, f"{method} {path} expected 401, got {r.status_code}"

    def test_public_endpoints_no_auth(self, base_url):
        s = requests.Session()
        assert s.get(f"{base_url}/api/", timeout=15).status_code == 200
        assert s.get(f"{base_url}/api/health/engine", timeout=15).status_code == 200


# ---------------- End-to-end user lifecycle (single class = single worker) ----------------
class TestUserLifecycle:
    """Create → enroll → recognize (single & multi) → attendance/history checks.

    All in one class so pytest-xdist loadscope keeps them on the same worker
    with a single shared user id (module-scoped fixture would otherwise be
    instantiated twice).
    """

    @pytest.fixture(scope="class")
    def _cleanup_prior(self, authed_client, base_url):
        """Delete any leftover TEST_ users from previous runs to keep gallery clean."""
        r = authed_client.get(f"{base_url}/api/users", timeout=15)
        if r.status_code == 200:
            for u in r.json():
                if str(u.get("name", "")).startswith("TEST_"):
                    authed_client.delete(f"{base_url}/api/users/{u['id']}", timeout=15)
        return True

    @pytest.fixture(scope="class")
    def user_id(self, authed_client, base_url, _cleanup_prior):
        payload = {
            "name": "TEST_Obama",
            "employee_id": "TEST_EMP_001",
            "department": "QA",
            "phone": "1234567890",
            "email": "TEST_obama@example.com",
        }
        r = authed_client.post(f"{base_url}/api/users", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "TEST_Obama"
        assert data["employee_id"] == "TEST_EMP_001"
        assert data["embeddings_count"] == 0
        uid = data["id"]
        yield uid
        try:
            authed_client.delete(f"{base_url}/api/users/{uid}", timeout=15)
        except Exception:
            pass

    # --- CRUD sanity ---
    def test_01_get_user(self, authed_client, base_url, user_id):
        r = authed_client.get(f"{base_url}/api/users/{user_id}", timeout=15)
        assert r.status_code == 200
        assert r.json()["id"] == user_id
        assert r.json()["name"] == "TEST_Obama"

    def test_02_list_users_contains_created(self, authed_client, base_url, user_id):
        r = authed_client.get(f"{base_url}/api/users", timeout=15)
        assert r.status_code == 200
        assert user_id in [u["id"] for u in r.json()]

    def test_03_get_missing_user_404(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/users/nonexistent-id-xyz", timeout=15)
        assert r.status_code == 404

    # --- Enrollment ---
    def test_04_enroll_success(self, authed_client, base_url, user_id, portrait_b64):
        r = authed_client.post(
            f"{base_url}/api/users/{user_id}/enroll",
            json={"images": [portrait_b64] * 4},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["saved"] > 0, f"No embeddings saved: {data}"
        assert data["total_embeddings"] > 0
        assert isinstance(data.get("rejected"), list)

    def test_05_enroll_rejects_no_face(self, authed_client, base_url, user_id, noise_b64):
        r = authed_client.post(
            f"{base_url}/api/users/{user_id}/enroll",
            json={"images": [noise_b64]},
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["rejected"]) >= 1
        assert data["rejected"][0]["index"] == 0

    def test_06_user_has_embeddings_and_thumbnail(self, authed_client, base_url, user_id):
        r = authed_client.get(f"{base_url}/api/users/{user_id}", timeout=15)
        assert r.status_code == 200
        u = r.json()
        assert u["embeddings_count"] > 0
        assert u.get("thumbnail_url", "").startswith("/uploads/users/")

    # --- Recognition ---
    def test_07_recognize_single_known(self, authed_client, base_url, user_id, portrait_b64):
        r = authed_client.post(f"{base_url}/api/recognize",
                               json={"image": portrait_b64, "camera_id": "test-cam"}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["detections"]) >= 1
        known = [d for d in data["detections"] if d.get("status") == "known"]
        assert known, f"No known detection: {data['detections']}"
        assert any(d["user_id"] == user_id for d in known), \
            f"Wrong user matched: {[d['user_id'] for d in known]} vs {user_id}"
        matched = next(d for d in known if d["user_id"] == user_id)
        assert matched["similarity"] >= 0.42

    def test_08_recognize_multi_known(self, authed_client, base_url, user_id, portrait_b64):
        r = authed_client.post(
            f"{base_url}/api/recognize/multi",
            json={"images": [portrait_b64] * 3, "camera_id": "test-cam"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "known", f"Expected known, got: {data}"
        assert data["user_id"] == user_id
        assert data["similarity"] >= 0.42
        assert "attendance_logged" in data

    def test_09_recognize_multi_no_face(self, authed_client, base_url, noise_b64):
        r = authed_client.post(
            f"{base_url}/api/recognize/multi",
            json={"images": [noise_b64] * 3, "camera_id": "test-cam"},
            timeout=60,
        )
        assert r.status_code == 200
        assert r.json()["status"] in ("no_face", "unknown")

    # --- Downstream lists ---
    def test_10_attendance_list(self, authed_client, base_url, user_id):
        r = authed_client.get(f"{base_url}/api/attendance?limit=200", timeout=15)
        assert r.status_code == 200
        matching = [x for x in r.json() if x.get("user_id") == user_id]
        assert matching, "No attendance logged for TEST_Obama"
        assert matching[0]["name"] == "TEST_Obama"
        assert matching[0]["employee_id"] == "TEST_EMP_001"

    def test_11_recognition_history(self, authed_client, base_url, user_id):
        r = authed_client.get(f"{base_url}/api/recognition-history?limit=200", timeout=15)
        assert r.status_code == 200
        assert any(x.get("user_id") == user_id for x in r.json())

    def test_12_unknowns_list(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/unknowns", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------- Dashboard ----------------
class TestDashboard:
    def test_stats_shape(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/dashboard/stats", timeout=15)
        assert r.status_code == 200
        data = r.json()
        for key in ("total_users", "today_attendance", "total_unknown",
                    "engine", "weekly_attendance", "avg_similarity", "match_threshold"):
            assert key in data, f"Missing key {key}"
        assert isinstance(data["weekly_attendance"], list)
        assert len(data["weekly_attendance"]) == 7
        assert data["engine"]["model"] == "buffalo_l"
        assert data["match_threshold"] == 0.42


# ---------------- Delete user ----------------
class TestDeleteUser:
    def test_delete_and_verify(self, authed_client, base_url):
        r = authed_client.post(f"{base_url}/api/users", json={"name": "TEST_Delete_Me"}, timeout=15)
        assert r.status_code == 200
        uid = r.json()["id"]
        r = authed_client.delete(f"{base_url}/api/users/{uid}", timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        r = authed_client.get(f"{base_url}/api/users/{uid}", timeout=15)
        assert r.status_code == 404
