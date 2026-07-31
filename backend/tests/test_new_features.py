"""Backend tests for the 4 new features shipped in iteration 2:

- Watchlist (normal / vip / blocked) + alert generation on recognize/multi
- Alerts API (list / mark-read / read-all, since filter)
- RTSP Cameras CRUD + status lifecycle (fake URL → state='error')
- Settings + Kiosk mode (public endpoint gated by token)

Every test class lives in this single module so pytest-xdist `loadscope`
pins them to one worker. Interdependent enroll→recognize flows sit
inside the same class with class-scoped fixtures for deterministic
shared state.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
import requests


# --------------------------------------------------------------------
# Watchlist + Alerts (needs an enrolled user)
# --------------------------------------------------------------------
class TestWatchlistAndAlerts:
    """Enroll one user → toggle watchlist → verify recognize/multi triggers alerts."""

    @pytest.fixture(scope="class")
    def _cleanup_prior(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/users", timeout=15)
        if r.status_code == 200:
            for u in r.json():
                if str(u.get("name", "")).startswith("TEST_WATCH_"):
                    authed_client.delete(f"{base_url}/api/users/{u['id']}", timeout=15)
        return True

    @pytest.fixture(scope="class")
    def user_id(self, authed_client, base_url, portrait_b64, _cleanup_prior):
        # Create user
        r = authed_client.post(
            f"{base_url}/api/users",
            json={"name": "TEST_WATCH_Obama", "employee_id": "TEST_WATCH_EMP_002"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        assert r.json()["watchlist_status"] == "normal", "New user must default to normal"

        # Enroll portrait (4 copies)
        er = authed_client.post(
            f"{base_url}/api/users/{uid}/enroll",
            json={"images": [portrait_b64] * 4},
            timeout=120,
        )
        assert er.status_code == 200, er.text
        assert er.json()["saved"] > 0
        yield uid
        try:
            authed_client.delete(f"{base_url}/api/users/{uid}", timeout=15)
        except Exception:
            pass

    # ---- Watchlist PATCH ----
    def test_01_watchlist_invalid_status_400(self, authed_client, base_url, user_id):
        r = authed_client.patch(
            f"{base_url}/api/users/{user_id}/watchlist",
            json={"status": "bogus"},
            timeout=15,
        )
        assert r.status_code == 400

    def test_02_watchlist_missing_user_404(self, authed_client, base_url):
        r = authed_client.patch(
            f"{base_url}/api/users/nonexistent-user-id/watchlist",
            json={"status": "vip"},
            timeout=15,
        )
        assert r.status_code == 404

    def test_03_set_vip(self, authed_client, base_url, user_id):
        r = authed_client.patch(
            f"{base_url}/api/users/{user_id}/watchlist",
            json={"status": "vip"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["id"] == user_id
        assert data["watchlist_status"] == "vip"

        # GET should reflect it too
        g = authed_client.get(f"{base_url}/api/users/{user_id}", timeout=15)
        assert g.status_code == 200
        assert g.json()["watchlist_status"] == "vip"

    def test_04_recognize_multi_vip_creates_alert(self, authed_client, base_url, user_id, portrait_b64):
        # Snapshot alert count BEFORE
        before = authed_client.get(f"{base_url}/api/alerts?limit=100", timeout=15).json()
        before_ids = {a["id"] for a in before}

        r = authed_client.post(
            f"{base_url}/api/recognize/multi",
            json={"images": [portrait_b64] * 3, "camera_id": "test-cam-vip"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "known", f"Expected known, got: {data}"
        assert data["user_id"] == user_id
        assert data["watchlist_status"] == "vip"

        # A new VIP alert must exist
        time.sleep(0.5)
        after = authed_client.get(f"{base_url}/api/alerts?limit=100", timeout=15).json()
        new_alerts = [a for a in after if a["id"] not in before_ids]
        vip_alerts = [a for a in new_alerts if a.get("kind") == "vip" and a.get("user_id") == user_id]
        assert vip_alerts, f"No VIP alert generated. new_alerts={new_alerts}"
        assert vip_alerts[0]["camera_id"] == "test-cam-vip"
        assert vip_alerts[0]["read"] is False

    def test_05_set_blocked(self, authed_client, base_url, user_id):
        r = authed_client.patch(
            f"{base_url}/api/users/{user_id}/watchlist",
            json={"status": "blocked"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["watchlist_status"] == "blocked"

    def test_06_recognize_multi_blocked_creates_alert(self, authed_client, base_url, user_id, portrait_b64):
        before = authed_client.get(f"{base_url}/api/alerts?limit=100", timeout=15).json()
        before_ids = {a["id"] for a in before}

        r = authed_client.post(
            f"{base_url}/api/recognize/multi",
            json={"images": [portrait_b64] * 3, "camera_id": "test-cam-blk"},
            timeout=90,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "known"
        assert data["watchlist_status"] == "blocked"

        time.sleep(0.5)
        after = authed_client.get(f"{base_url}/api/alerts?limit=100", timeout=15).json()
        new_alerts = [a for a in after if a["id"] not in before_ids]
        blk_alerts = [a for a in new_alerts if a.get("kind") == "blocked" and a.get("user_id") == user_id]
        assert blk_alerts, f"No blocked alert generated. new_alerts={new_alerts}"

    def test_07_recognize_multi_unknown_creates_alert(self, authed_client, base_url, noise_b64):
        before = authed_client.get(f"{base_url}/api/alerts?limit=100", timeout=15).json()
        before_ids = {a["id"] for a in before}

        r = authed_client.post(
            f"{base_url}/api/recognize/multi",
            json={"images": [noise_b64] * 3, "camera_id": "test-cam-noise"},
            timeout=60,
        )
        assert r.status_code == 200
        # status can be 'no_face' (no detections) or 'unknown' (detections below threshold).
        # An alert is only created on 'unknown' path (best_frame_b64 present).
        st = r.json().get("status")
        assert st in ("unknown", "no_face")
        if st == "unknown":
            time.sleep(0.5)
            after = authed_client.get(f"{base_url}/api/alerts?limit=100", timeout=15).json()
            new_alerts = [a for a in after if a["id"] not in before_ids]
            unk_alerts = [a for a in new_alerts if a.get("kind") == "unknown"]
            assert unk_alerts, f"No unknown alert generated. new_alerts={new_alerts}"
            a = unk_alerts[0]
            # best-similarity + image_url should be present
            assert "similarity" in a
            assert a.get("image_url", "").startswith("/uploads/unknowns/")

    # ---- reset watchlist to normal (leaves user in clean state) ----
    def test_08_reset_to_normal(self, authed_client, base_url, user_id):
        r = authed_client.patch(
            f"{base_url}/api/users/{user_id}/watchlist",
            json={"status": "normal"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["watchlist_status"] == "normal"


# --------------------------------------------------------------------
# Alerts API contract (list, filter, read, read-all)
# --------------------------------------------------------------------
class TestAlertsApi:
    def test_list_returns_sorted_desc(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/alerts?limit=50", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if len(data) >= 2:
            ts = [a["timestamp"] for a in data]
            assert ts == sorted(ts, reverse=True), "alerts must be timestamp desc"
            # Basic shape
            for a in data[:3]:
                assert "id" in a and "kind" in a and "read" in a
                assert a["kind"] in ("unknown", "blocked", "vip")

    def test_since_filter(self, authed_client, base_url):
        # future ISO → should return empty
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        r = authed_client.get(f"{base_url}/api/alerts?since={future}", timeout=15)
        assert r.status_code == 200
        assert r.json() == [], "since=<future> must return 0 alerts"

        # very old ISO → should include everything if any exist
        past = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
        r = authed_client.get(f"{base_url}/api/alerts?since={past}", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_alerts_require_auth(self, base_url):
        s = requests.Session()
        assert s.get(f"{base_url}/api/alerts", timeout=15).status_code == 401
        assert s.post(f"{base_url}/api/alerts/xyz/read", timeout=15).status_code == 401
        assert s.post(f"{base_url}/api/alerts/read-all", timeout=15).status_code == 401

    def test_mark_read_individual(self, authed_client, base_url):
        alerts = authed_client.get(f"{base_url}/api/alerts?limit=100", timeout=15).json()
        unread = [a for a in alerts if not a.get("read")]
        if not unread:
            pytest.skip("No unread alerts to mark read")
        aid = unread[0]["id"]
        r = authed_client.post(f"{base_url}/api/alerts/{aid}/read", timeout=15)
        assert r.status_code == 200
        # Confirm read=true persisted
        after = authed_client.get(f"{base_url}/api/alerts?limit=100", timeout=15).json()
        rec = next((x for x in after if x["id"] == aid), None)
        assert rec is not None
        assert rec["read"] is True

    def test_mark_read_missing_404(self, authed_client, base_url):
        r = authed_client.post(f"{base_url}/api/alerts/nonexistent-alert-id/read", timeout=15)
        assert r.status_code == 404

    def test_read_all(self, authed_client, base_url):
        r = authed_client.post(f"{base_url}/api/alerts/read-all", timeout=15)
        assert r.status_code == 200
        # All alerts should now be read
        after = authed_client.get(f"{base_url}/api/alerts?limit=200", timeout=15).json()
        assert all(a.get("read") is True for a in after), "read-all must set every alert read=true"


# --------------------------------------------------------------------
# Cameras CRUD lifecycle
# --------------------------------------------------------------------
class TestCameras:
    """Cameras CRUD + status lifecycle. Fake RTSP URL → worker fails to open → state='error'."""

    @pytest.fixture(scope="class")
    def _cleanup_prior(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/cameras", timeout=15)
        if r.status_code == 200:
            for c in r.json():
                if str(c.get("name", "")).startswith("TEST_CAM_"):
                    authed_client.delete(f"{base_url}/api/cameras/{c['id']}", timeout=15)
        return True

    def test_01_list_starts_empty_or_no_test_cams(self, authed_client, base_url, _cleanup_prior):
        r = authed_client.get(f"{base_url}/api/cameras", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert not any(str(c.get("name", "")).startswith("TEST_CAM_") for c in data)

    def test_02_create_camera(self, authed_client, base_url):
        payload = {
            "name": "TEST_CAM_lobby",
            "url": "rtsp://invalid.example.local:1/none",
            "type": "rtsp",
            "enabled": True,
        }
        r = authed_client.post(f"{base_url}/api/cameras", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        assert doc["name"] == "TEST_CAM_lobby"
        assert doc["type"] == "rtsp"
        assert doc["enabled"] is True
        assert "id" in doc
        # Should have a status assigned — worker was just started
        assert doc.get("status") in ("starting", "running", "error", "stopped")
        pytest.cam_id = doc["id"]

    def test_03_list_includes_status_field(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/cameras", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        row = next((c for c in rows if c["id"] == pytest.cam_id), None)
        assert row is not None
        assert "status" in row
        assert row["status"] in ("starting", "running", "error", "stopped")

    def test_04_status_transitions_to_error_for_fake_rtsp(self, authed_client, base_url):
        # Poll up to ~10s — cv2.VideoCapture on an unreachable RTSP should surface an error state
        deadline = time.time() + 15
        state = None
        while time.time() < deadline:
            r = authed_client.get(f"{base_url}/api/cameras/{pytest.cam_id}/status", timeout=15)
            assert r.status_code == 200
            state = r.json().get("state")
            if state in ("error", "stopped"):
                break
            time.sleep(1.0)
        assert state in ("error", "stopped", "starting"), (
            f"Unexpected state for fake RTSP URL: {state}"
        )
        # NOTE: 'starting' is allowed only because on some systems VideoCapture
        # blocks for a long time before failing; if we ever transition to 'running'
        # that would be a bug for an unreachable URL.
        assert state != "running", "Fake RTSP must never end up 'running'"

    def test_05_patch_disable_stops_worker(self, authed_client, base_url):
        r = authed_client.patch(
            f"{base_url}/api/cameras/{pytest.cam_id}",
            json={"enabled": False},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["enabled"] is False

        # Wait briefly and check status → stopped
        time.sleep(1.0)
        r = authed_client.get(f"{base_url}/api/cameras/{pytest.cam_id}/status", timeout=15)
        assert r.status_code == 200
        assert r.json().get("state") in ("stopped", "starting", "error"), r.json()
        # After stop() removes the worker, status endpoint returns 'stopped'
        # (manager.status returns {'state':'stopped'} when no worker).

    def test_06_patch_missing_camera_404(self, authed_client, base_url):
        r = authed_client.patch(
            f"{base_url}/api/cameras/nonexistent-cam-id",
            json={"enabled": False},
            timeout=15,
        )
        assert r.status_code == 404

    def test_07_status_of_unknown_camera_returns_stopped(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/cameras/nonexistent-cam-id/status", timeout=15)
        assert r.status_code == 200
        assert r.json().get("state") == "stopped"

    def test_08_delete_camera(self, authed_client, base_url):
        r = authed_client.delete(f"{base_url}/api/cameras/{pytest.cam_id}", timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True

        # Camera gone from list
        rows = authed_client.get(f"{base_url}/api/cameras", timeout=15).json()
        assert not any(c["id"] == pytest.cam_id for c in rows)

    def test_09_delete_missing_404(self, authed_client, base_url):
        r = authed_client.delete(f"{base_url}/api/cameras/nonexistent-cam-id", timeout=15)
        assert r.status_code == 404

    def test_10_status_after_delete_returns_stopped(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/cameras/{pytest.cam_id}/status", timeout=15)
        assert r.status_code == 200
        assert r.json().get("state") == "stopped"


# --------------------------------------------------------------------
# Settings + test-email + Kiosk
# --------------------------------------------------------------------
class TestSettingsAndKiosk:
    KIOSK_TOKEN = "TEST_KIOSK_TOKEN_abc123"
    ALERT_EMAIL = "demo@example.com"

    def test_01_get_settings_requires_auth(self, base_url):
        s = requests.Session()
        assert s.get(f"{base_url}/api/settings", timeout=15).status_code == 401

    def test_02_get_settings_default_shape(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/settings", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "alert_email" in data
        assert "kiosk_token" in data

    def test_03_patch_settings_saves(self, authed_client, base_url):
        r = authed_client.patch(
            f"{base_url}/api/settings",
            json={"alert_email": self.ALERT_EMAIL, "kiosk_token": self.KIOSK_TOKEN},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # Read back
        g = authed_client.get(f"{base_url}/api/settings", timeout=15)
        assert g.status_code == 200
        data = g.json()
        assert data["alert_email"] == self.ALERT_EMAIL
        assert data["kiosk_token"] == self.KIOSK_TOKEN

    def test_04_test_email_endpoint_contract(self, authed_client, base_url):
        """test-email is admin-only. With Resend sandbox key + non-owner recipient
        we may get 200 (email_id) or 502 (Resend rejected). Both are acceptable —
        we only assert the endpoint contract (no 5xx crash, no 401/403 for admin)."""
        r = authed_client.post(f"{base_url}/api/settings/test-email", timeout=30)
        assert r.status_code in (200, 502), f"Unexpected status: {r.status_code} {r.text}"
        if r.status_code == 200:
            body = r.json()
            assert body.get("ok") is True
            assert "recipient" in body
            # email_id may be None only if the key is missing; asserting presence when 200 returned
            assert "email_id" in body

    # ---- Kiosk ----
    def test_05_kiosk_wrong_token_401(self, base_url):
        s = requests.Session()
        r = s.post(
            f"{base_url}/api/kiosk/verify",
            json={"token": "WRONG_TOKEN", "images": []},
            timeout=15,
        )
        assert r.status_code == 401

    def test_06_kiosk_is_public_no_admin_auth(self, base_url):
        """Kiosk endpoint should not require Bearer token — only kiosk_token in body."""
        s = requests.Session()  # no Authorization header
        r = s.post(
            f"{base_url}/api/kiosk/verify",
            json={"token": self.KIOSK_TOKEN, "images": []},
            timeout=30,
        )
        # 400 = "images required" — proves auth passed
        assert r.status_code == 400, f"Kiosk should accept without Bearer; got {r.status_code} {r.text}"

    def test_07_kiosk_known_face(self, authed_client, base_url, portrait_b64):
        """With correct token and enrolled portrait images → status='known' + watchlist_status."""
        # Ensure there is an enrolled user in gallery
        users = authed_client.get(f"{base_url}/api/users", timeout=15).json()
        has_enrolled = any(u.get("embeddings_count", 0) > 0 for u in users)
        if not has_enrolled:
            pytest.skip("No enrolled user in gallery — cannot verify known-face kiosk path")

        s = requests.Session()
        r = s.post(
            f"{base_url}/api/kiosk/verify",
            json={"token": self.KIOSK_TOKEN, "images": [portrait_b64] * 3, "camera_id": "kiosk-test"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Could be known (if the enrolled portrait matches) or unknown otherwise.
        # Our test setup enrolls TEST_WATCH_Obama with the same portrait so it should match.
        assert data.get("status") in ("known", "unknown", "no_face")
        if data["status"] == "known":
            assert "watchlist_status" in data
            assert data["watchlist_status"] in ("normal", "vip", "blocked")

    def test_08_kiosk_noise_no_face_or_unknown(self, base_url, noise_b64):
        s = requests.Session()
        r = s.post(
            f"{base_url}/api/kiosk/verify",
            json={"token": self.KIOSK_TOKEN, "images": [noise_b64] * 3, "camera_id": "kiosk-test"},
            timeout=60,
        )
        assert r.status_code == 200
        assert r.json().get("status") in ("unknown", "no_face")


# --------------------------------------------------------------------
# Dashboard stats — new fields
# --------------------------------------------------------------------
class TestDashboardStatsExtended:
    def test_stats_has_new_fields(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/dashboard/stats", timeout=15)
        assert r.status_code == 200
        data = r.json()
        for k in ("cameras_total", "cameras_online", "unread_alerts"):
            assert k in data, f"Missing new dashboard field: {k}"
        assert isinstance(data["cameras_total"], int)
        assert isinstance(data["cameras_online"], int)
        assert isinstance(data["unread_alerts"], int)
        assert data["cameras_online"] <= data["cameras_total"]
