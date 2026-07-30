"""Backend tests for iteration 3 (retail transformation).

Covers:
- Retail fields on POST/PATCH/GET /api/users (gender, dob, address, notes,
  loyalty_points) + read-only visit/spend fields.
- Register-from-unknown workflow (unknown record → new user with 1 embedding
  + thumbnail, unknown row deleted, subsequent recognition returns known).
- Visit tracking via recognize/multi: total_visits increments once per day.
- Purchases CRUD + lifetime_spend / loyalty_points bookkeeping.
- Reports: overview, top-spenders, frequent-visitors, vips, send-digest.

All tests live in one class so pytest-xdist loadscope pins them to one worker
(interdependent enroll→recognize→purchases flow with shared retail user_id).

Uses /app/test_fixtures/t1.jpg (a group photo with a face DIFFERENT from
portrait.jpg's Obama face) so this class does not clash with TEST_Obama /
TEST_WATCH_Obama enrolled by the parallel TestUserLifecycle /
TestWatchlistAndAlerts classes.
"""
from __future__ import annotations

import base64
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

FIXTURES = Path("/app/test_fixtures")


def _b64_of(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()


@pytest.fixture(scope="session")
def t1_b64():
    return _b64_of(FIXTURES / "t1.jpg")


# --------------------------------------------------------------------
# Retail features - full flow
# --------------------------------------------------------------------
class TestRetailFeatures:

    @pytest.fixture(scope="class", autouse=True)
    def _cleanup(self, authed_client, base_url):
        """Purge any TEST_RETAIL_ leftovers (users, purchases, unknowns) from
        prior runs. Runs before + after this class."""
        def _do():
            # Users + embeddings
            r = authed_client.get(f"{base_url}/api/users", timeout=15)
            if r.status_code == 200:
                for u in r.json():
                    if str(u.get("name", "")).startswith("TEST_RETAIL_"):
                        authed_client.delete(f"{base_url}/api/users/{u['id']}", timeout=15)
            # Purchases (list, filter by user_id would already be removed via user delete,
            # but stray docs may remain — try to filter by invoice prefix)
            r = authed_client.get(f"{base_url}/api/purchases?limit=500", timeout=15)
            if r.status_code == 200:
                for p in r.json():
                    if str(p.get("invoice_number", "")).startswith("TEST_RETAIL_"):
                        authed_client.delete(f"{base_url}/api/purchases/{p['id']}", timeout=15)
            # Unknowns
            r = authed_client.get(f"{base_url}/api/unknowns?limit=500", timeout=15)
            if r.status_code == 200:
                for uk in r.json():
                    # only wipe those from our own camera_id to avoid nuking real ones
                    if str(uk.get("camera_id", "")).startswith("TEST_RETAIL_"):
                        authed_client.delete(f"{base_url}/api/unknowns/{uk['id']}", timeout=15)
        _do()
        yield
        _do()

    # --------------------------------------------------------------
    # 01. Create user with retail fields
    # --------------------------------------------------------------
    def test_01_create_user_with_retail_fields(self, authed_client, base_url):
        payload = {
            "name": "TEST_RETAIL_Alice",
            "phone": "555-0100",
            "gender": "F",
            "dob": "1990-05-12",
            "address": "42 Retail Ave, Metropolis",
            "notes": "Prefers loyalty rewards",
            "loyalty_points": 25,
        }
        r = authed_client.post(f"{base_url}/api/users", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["name"] == "TEST_RETAIL_Alice"
        assert u["gender"] == "F"
        assert u["dob"] == "1990-05-12"
        assert u["address"] == "42 Retail Ave, Metropolis"
        assert u["notes"] == "Prefers loyalty rewards"
        assert u["loyalty_points"] == 25
        # Read-only visit/spend fields must default to 0/null
        assert u["total_visits"] == 0
        assert u["lifetime_spend"] == 0.0
        assert u["last_visit_at"] is None
        assert u["watchlist_status"] == "normal"
        pytest.retail_alice_id = u["id"]

    # --------------------------------------------------------------
    # 02. PATCH retail fields; unknown fields ignored
    # --------------------------------------------------------------
    def test_02_patch_retail_fields_ignore_unknown(self, authed_client, base_url):
        uid = pytest.retail_alice_id
        body = {
            "address": "99 New St",
            "loyalty_points": 100,
            "notes": "Updated notes",
            # These must be silently ignored (not in allowlist)
            "watchlist_status": "vip",
            "total_visits": 999,
            "lifetime_spend": 12345,
            "bogus_field": "haha",
        }
        r = authed_client.patch(f"{base_url}/api/users/{uid}", json=body, timeout=15)
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["address"] == "99 New St"
        assert u["loyalty_points"] == 100
        assert u["notes"] == "Updated notes"
        # Ignored fields must remain default
        assert u["watchlist_status"] == "normal", "watchlist_status must be ignored by PATCH /users"
        assert u["total_visits"] == 0, "total_visits must be ignored by PATCH /users"
        assert u["lifetime_spend"] == 0.0, "lifetime_spend must be ignored by PATCH /users"
        # UserOut shape sanity
        for k in ("total_visits", "lifetime_spend", "last_visit_at"):
            assert k in u

    def test_03_patch_empty_body_400(self, authed_client, base_url):
        uid = pytest.retail_alice_id
        r = authed_client.patch(f"{base_url}/api/users/{uid}", json={"unknown_only": 1}, timeout=15)
        assert r.status_code == 400

    def test_04_patch_missing_user_404(self, authed_client, base_url):
        r = authed_client.patch(f"{base_url}/api/users/nonexistent-retail-id",
                                json={"notes": "x"}, timeout=15)
        assert r.status_code == 404

    # --------------------------------------------------------------
    # 05. List users returns visit/spend fields
    # --------------------------------------------------------------
    def test_05_list_users_has_new_fields(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/users", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert rows, "user list must not be empty"
        for u in rows[:5]:
            for k in ("total_visits", "lifetime_spend", "last_visit_at",
                      "gender", "dob", "address", "notes", "loyalty_points"):
                assert k in u, f"UserOut missing field: {k}"
        alice = next((u for u in rows if u["id"] == pytest.retail_alice_id), None)
        assert alice is not None
        assert alice["total_visits"] == 0
        assert alice["lifetime_spend"] == 0.0

    # --------------------------------------------------------------
    # 06. Register-from-unknown flow
    # --------------------------------------------------------------
    def test_06_register_from_unknown_flow(self, authed_client, base_url, t1_b64):
        # 6a) POST recognize/multi 3x with a t1.jpg face (does NOT match any
        # existing enrolled user — group photo with different faces).
        # This creates an unknown record with the image saved to disk.
        r = authed_client.post(
            f"{base_url}/api/recognize/multi",
            json={"images": [t1_b64] * 3, "camera_id": "TEST_RETAIL_cam"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Must yield an unknown with a saved unknown_id (face was detected but
        # doesn't match anyone → best_frame_b64 saved via _save_unknown)
        assert data.get("status") == "unknown", f"Expected unknown, got: {data}"
        assert data.get("unknown_id"), f"unknown_id missing: {data}"
        unknown_id = data["unknown_id"]

        # 6b) Register the unknown as a new user
        reg = authed_client.post(
            f"{base_url}/api/register-from-unknown",
            json={
                "unknown_id": unknown_id,
                "name": "TEST_RETAIL_Bob",
                "phone": "555-0200",
                "gender": "M",
                "notes": "converted from unknown capture",
            },
            timeout=90,
        )
        assert reg.status_code == 200, reg.text
        new_user = reg.json()
        assert new_user["name"] == "TEST_RETAIL_Bob"
        assert new_user["phone"] == "555-0200"
        assert new_user["gender"] == "M"
        assert new_user["embeddings_count"] == 1
        assert new_user["thumbnail_url"], "thumbnail_url must be set"
        assert new_user["thumbnail_url"].startswith("/uploads/users/")
        pytest.retail_bob_id = new_user["id"]

        # 6c) Unknown row must be gone
        uk_list = authed_client.get(f"{base_url}/api/unknowns?limit=500", timeout=15).json()
        assert not any(x["id"] == unknown_id for x in uk_list), \
            "unknown record must be deleted after register-from-unknown"

        # 6d) Re-run recognize/multi with same t1.jpg → should now match Bob
        r2 = authed_client.post(
            f"{base_url}/api/recognize/multi",
            json={"images": [t1_b64] * 3, "camera_id": "TEST_RETAIL_cam"},
            timeout=90,
        )
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2.get("status") == "known", f"Expected known after registration, got: {d2}"
        assert d2["user_id"] == pytest.retail_bob_id, \
            f"Wrong user matched: {d2.get('user_id')} vs bob={pytest.retail_bob_id}"
        assert d2["similarity"] >= 0.42

    # --------------------------------------------------------------
    # 07. Register-from-unknown 404 for bad unknown_id
    # --------------------------------------------------------------
    def test_07_register_from_unknown_404(self, authed_client, base_url):
        r = authed_client.post(
            f"{base_url}/api/register-from-unknown",
            json={"unknown_id": "does-not-exist-xyz", "name": "TEST_RETAIL_Ghost"},
            timeout=30,
        )
        assert r.status_code == 404

    # --------------------------------------------------------------
    # 08. Visit tracking: total_visits increments ONCE per day
    # --------------------------------------------------------------
    def test_08_recognize_multi_visits_increment_once_per_day(
        self, authed_client, base_url, t1_b64
    ):
        uid = pytest.retail_bob_id
        # After test_06 there were 2 recognize/multi calls that produced a
        # 'known' result (only the second one, the first was 'unknown').
        # Fetch current state.
        u = authed_client.get(f"{base_url}/api/users/{uid}", timeout=15).json()
        visits_before = int(u["total_visits"])
        last_before = u["last_visit_at"]
        assert visits_before >= 1, f"expected at least 1 visit after test_06, got {visits_before}"
        assert last_before, "last_visit_at must be set after recognize/multi hit"

        # Fire recognize/multi again — same calendar day → NO increment
        r = authed_client.post(
            f"{base_url}/api/recognize/multi",
            json={"images": [t1_b64] * 3, "camera_id": "TEST_RETAIL_cam"},
            timeout=90,
        )
        assert r.status_code == 200
        assert r.json().get("status") == "known"

        u2 = authed_client.get(f"{base_url}/api/users/{uid}", timeout=15).json()
        assert u2["total_visits"] == visits_before, (
            f"total_visits must NOT double-increment same day: "
            f"before={visits_before}, after={u2['total_visits']}"
        )

    # --------------------------------------------------------------
    # 09. Purchases: create → lifetime_spend + loyalty_points increment
    # --------------------------------------------------------------
    def test_09_create_purchase(self, authed_client, base_url):
        uid = pytest.retail_alice_id  # Alice starts clean (spend=0, points=100 from patch)
        # Snapshot before
        u0 = authed_client.get(f"{base_url}/api/users/{uid}", timeout=15).json()
        spend_before = float(u0["lifetime_spend"])
        pts_before = int(u0["loyalty_points"])

        body = {
            "user_id": uid,
            "invoice_number": "TEST_RETAIL_INV_001",
            "items": [
                {"product": "Widget A", "price": 45.0, "quantity": 2, "discount": 0},
                {"product": "Widget B", "price": 30.0, "quantity": 1, "discount": 5},
            ],
            "total": 115.0,   # explicit total (2*45 + 30 - 5 = 115)
            "payment_mode": "card",
        }
        r = authed_client.post(f"{base_url}/api/purchases", json=body, timeout=30)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["user_id"] == uid
        assert p["total"] == 115.0
        assert p["invoice_number"] == "TEST_RETAIL_INV_001"
        assert p["payment_mode"] == "card"
        assert len(p["items"]) == 2
        pytest.retail_purchase_id = p["id"]

        # Verify user increments
        u1 = authed_client.get(f"{base_url}/api/users/{uid}", timeout=15).json()
        assert abs(u1["lifetime_spend"] - (spend_before + 115.0)) < 0.01
        # loyalty = int(total // 10) = 11
        assert u1["loyalty_points"] == pts_before + 11, \
            f"loyalty_points: expected {pts_before + 11}, got {u1['loyalty_points']}"

    # --------------------------------------------------------------
    # 10. GET /api/purchases?user_id=<id> returns the just-created row
    # --------------------------------------------------------------
    def test_10_list_purchases_by_user(self, authed_client, base_url):
        uid = pytest.retail_alice_id
        r = authed_client.get(f"{base_url}/api/purchases?user_id={uid}", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert any(p["id"] == pytest.retail_purchase_id for p in rows), \
            "just-created purchase must appear in filtered list"
        row = next(p for p in rows if p["id"] == pytest.retail_purchase_id)
        assert row["total"] == 115.0
        assert row["invoice_number"] == "TEST_RETAIL_INV_001"

    # --------------------------------------------------------------
    # 11. GET /api/purchases (no user_id) returns customer_name-attached rows
    # --------------------------------------------------------------
    def test_11_list_all_purchases_has_customer_name(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/purchases?limit=100", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert rows, "expected at least our just-created purchase"
        ours = next((p for p in rows if p["id"] == pytest.retail_purchase_id), None)
        assert ours is not None
        assert ours.get("customer_name") == "TEST_RETAIL_Alice", \
            f"customer_name expected 'TEST_RETAIL_Alice', got {ours.get('customer_name')}"

    # --------------------------------------------------------------
    # 12. DELETE purchase reverses increments; requires admin
    # --------------------------------------------------------------
    def test_12_delete_purchase_reverses_increments(self, authed_client, base_url):
        uid = pytest.retail_alice_id
        u0 = authed_client.get(f"{base_url}/api/users/{uid}", timeout=15).json()
        spend_before = float(u0["lifetime_spend"])
        pts_before = int(u0["loyalty_points"])

        r = authed_client.delete(f"{base_url}/api/purchases/{pytest.retail_purchase_id}", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        u1 = authed_client.get(f"{base_url}/api/users/{uid}", timeout=15).json()
        assert abs(u1["lifetime_spend"] - (spend_before - 115.0)) < 0.01, \
            f"lifetime_spend must decrement by 115: before={spend_before}, after={u1['lifetime_spend']}"
        assert u1["loyalty_points"] == pts_before - 11, \
            f"loyalty_points must decrement by 11: before={pts_before}, after={u1['loyalty_points']}"

        # And confirm the purchase row is gone
        rows = authed_client.get(f"{base_url}/api/purchases?user_id={uid}", timeout=15).json()
        assert not any(p["id"] == pytest.retail_purchase_id for p in rows)

    def test_13_delete_purchase_404(self, authed_client, base_url):
        r = authed_client.delete(f"{base_url}/api/purchases/nonexistent-purchase-id", timeout=15)
        assert r.status_code == 404

    # --------------------------------------------------------------
    # 14. Reports: overview
    # --------------------------------------------------------------
    def test_14_reports_overview_shape(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/reports/overview?days=7", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("days", "total_visits", "unique_visitors", "unknown", "vip_visits", "peak_hours"):
            assert k in data, f"missing key {k}"
        assert data["days"] == 7
        assert isinstance(data["peak_hours"], list)
        assert isinstance(data["total_visits"], int)
        assert isinstance(data["unique_visitors"], int)
        assert isinstance(data["unknown"], int)
        assert isinstance(data["vip_visits"], int)
        # Bob's attendance from test_06 should show up
        assert data["total_visits"] >= 1

    # --------------------------------------------------------------
    # 15. Reports: top-spenders
    # --------------------------------------------------------------
    def test_15_reports_top_spenders(self, authed_client, base_url):
        # After test_12 Alice's spend is back to 0. Create a new purchase for Alice
        # so top-spenders has data to return.
        uid = pytest.retail_alice_id
        r = authed_client.post(
            f"{base_url}/api/purchases",
            json={
                "user_id": uid,
                "invoice_number": "TEST_RETAIL_INV_002",
                "items": [{"product": "TopSpend", "price": 250.0, "quantity": 1, "discount": 0}],
                "total": 250.0,
                "payment_mode": "cash",
            },
            timeout=30,
        )
        assert r.status_code == 200
        pytest.retail_purchase2_id = r.json()["id"]

        r = authed_client.get(f"{base_url}/api/reports/top-spenders?limit=20", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert rows, "top-spenders should include at least Alice"
        for u in rows:
            assert u["lifetime_spend"] > 0, \
                f"top-spenders must only include users with spend>0, got {u['lifetime_spend']}"
        # Sorted desc
        spends = [u["lifetime_spend"] for u in rows]
        assert spends == sorted(spends, reverse=True), "top-spenders must be sorted desc"
        alice = next((u for u in rows if u["id"] == uid), None)
        assert alice is not None, "Alice with fresh 250 spend must appear"
        assert alice["lifetime_spend"] >= 250.0

    # --------------------------------------------------------------
    # 16. Reports: frequent-visitors
    # --------------------------------------------------------------
    def test_16_reports_frequent_visitors(self, authed_client, base_url):
        r = authed_client.get(f"{base_url}/api/reports/frequent-visitors?days=30", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        # Bob should have >=1 visit from test_06
        bob = next((u for u in rows if u["id"] == pytest.retail_bob_id), None)
        if bob:
            assert "recent_visits" in bob
            assert "most_recent_at" in bob
            assert bob["recent_visits"] >= 1

    # --------------------------------------------------------------
    # 17. Reports: vips
    # --------------------------------------------------------------
    def test_17_reports_vips(self, authed_client, base_url):
        # Set Bob to vip
        uid = pytest.retail_bob_id
        r = authed_client.patch(
            f"{base_url}/api/users/{uid}/watchlist",
            json={"status": "vip"},
            timeout=15,
        )
        assert r.status_code == 200

        r = authed_client.get(f"{base_url}/api/reports/vips", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert any(u["id"] == uid and u["watchlist_status"] == "vip" for u in rows)

        # Reset to normal
        authed_client.patch(
            f"{base_url}/api/users/{uid}/watchlist",
            json={"status": "normal"},
            timeout=15,
        )

    # --------------------------------------------------------------
    # 18. Reports: send-digest (contract only)
    # --------------------------------------------------------------
    def test_18_send_digest_400_when_alert_email_missing(self, base_url, auth_token):
        """Directly wipe settings.alert_email in Mongo, hit endpoint, then restore.
        Endpoint must 400 when no recipient is configured."""
        import pymongo
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "test_database")
        # Read backend .env if not exposed to test env
        if "MONGO_URL" not in os.environ or "DB_NAME" not in os.environ:
            env_path = Path("/app/backend/.env")
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("MONGO_URL"):
                        mongo_url = line.split("=", 1)[1].strip().strip('"')
                    elif line.startswith("DB_NAME"):
                        db_name = line.split("=", 1)[1].strip().strip('"')

        c = pymongo.MongoClient(mongo_url)
        settings_col = c[db_name]["settings"]
        current = settings_col.find_one({"_id": "notifications"}) or {}
        prev_email = current.get("alert_email")
        try:
            settings_col.update_one(
                {"_id": "notifications"},
                {"$set": {"alert_email": ""}},
                upsert=True,
            )
            # Also unset env fallback for the duration of this check
            s = requests.Session()
            s.headers.update({"Authorization": f"Bearer {auth_token}",
                              "Content-Type": "application/json"})
            r = s.post(f"{base_url}/api/reports/send-digest", timeout=30)
            # If backend has ALERT_TO fallback and it's set, this will not 400.
            # backend/.env sets ALERT_TO='' → fallback is empty → expect 400.
            assert r.status_code == 400, f"Expected 400 with empty alert_email, got {r.status_code}: {r.text}"
        finally:
            # Restore
            if prev_email is not None:
                settings_col.update_one(
                    {"_id": "notifications"},
                    {"$set": {"alert_email": prev_email}},
                    upsert=True,
                )
            c.close()

    def test_19_send_digest_contract_with_email(self, authed_client, base_url):
        """With alert_email set, endpoint returns 200 (with email_id, recipient, data)
        or 502 (Resend sandbox rejects). Both are acceptable per spec."""
        # Ensure a recipient is configured
        authed_client.patch(
            f"{base_url}/api/settings",
            json={"alert_email": "demo@example.com"},
            timeout=15,
        )
        r = authed_client.post(f"{base_url}/api/reports/send-digest", timeout=60)
        assert r.status_code in (200, 502), f"Unexpected status {r.status_code}: {r.text}"
        if r.status_code == 200:
            body = r.json()
            assert body.get("ok") is True
            assert "email_id" in body
            assert body.get("recipient") == "demo@example.com"
            assert "data" in body
            data = body["data"]
            for k in ("period_start", "period_end", "total_visits",
                      "unique_visitors", "vip_visits", "total_unknown",
                      "top_spenders", "frequent_visitors"):
                assert k in data, f"digest data missing key {k}"

    def test_20_send_digest_requires_admin(self, base_url):
        s = requests.Session()  # unauthenticated
        r = s.post(f"{base_url}/api/reports/send-digest", timeout=15)
        assert r.status_code == 401

    # --------------------------------------------------------------
    # 21. Regression sanity: create purchase auto-total from items
    # --------------------------------------------------------------
    def test_21_create_purchase_auto_total_from_items(self, authed_client, base_url):
        uid = pytest.retail_alice_id
        u0 = authed_client.get(f"{base_url}/api/users/{uid}", timeout=15).json()
        spend_before = float(u0["lifetime_spend"])
        pts_before = int(u0["loyalty_points"])

        body = {
            "user_id": uid,
            "invoice_number": "TEST_RETAIL_INV_003",
            "items": [
                {"product": "X", "price": 10.0, "quantity": 3, "discount": 2},  # 28
                {"product": "Y", "price": 20.0, "quantity": 1, "discount": 0},  # 20
            ],
            # No total provided → server computes from items = 48
            "total": 0,
            "payment_mode": "upi",
        }
        r = authed_client.post(f"{base_url}/api/purchases", json=body, timeout=30)
        assert r.status_code == 200, r.text
        p = r.json()
        assert abs(p["total"] - 48.0) < 0.01, f"auto-total should be 48, got {p['total']}"

        u1 = authed_client.get(f"{base_url}/api/users/{uid}", timeout=15).json()
        assert abs(u1["lifetime_spend"] - (spend_before + 48.0)) < 0.01
        assert u1["loyalty_points"] == pts_before + 4  # floor(48/10) = 4

        # Cleanup
        authed_client.delete(f"{base_url}/api/purchases/{p['id']}", timeout=15)

    # --------------------------------------------------------------
    # 22. Reports require auth
    # --------------------------------------------------------------
    def test_22_reports_require_auth(self, base_url):
        s = requests.Session()
        for path in ("/api/reports/overview", "/api/reports/top-spenders",
                     "/api/reports/frequent-visitors", "/api/reports/vips"):
            r = s.get(f"{base_url}{path}", timeout=15)
            assert r.status_code == 401, f"{path} expected 401, got {r.status_code}"

    # --------------------------------------------------------------
    # 23. Purchases list requires auth
    # --------------------------------------------------------------
    def test_23_purchases_require_auth(self, base_url):
        s = requests.Session()
        assert s.get(f"{base_url}/api/purchases", timeout=15).status_code == 401
        assert s.post(f"{base_url}/api/purchases", json={}, timeout=15).status_code == 401
