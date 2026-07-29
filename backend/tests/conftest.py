"""Pytest fixtures for Face Recognition backend tests."""
import base64
import os
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if "REACT_APP_BACKEND_URL" in os.environ else None
if not BASE_URL:
    # fallback to reading frontend/.env
    _env_path = Path("/app/frontend/.env")
    for line in _env_path.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
            break

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

FIXTURES = Path("/app/test_fixtures")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def auth_token(api_client):
    r = api_client.post(f"{BASE_URL}/api/auth/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code} {r.text}")
    return r.json()["token"]


@pytest.fixture(scope="session")
def authed_client(auth_token):
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    })
    return s


def _b64(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


@pytest.fixture(scope="session")
def portrait_b64():
    return _b64(FIXTURES / "portrait.jpg")


@pytest.fixture(scope="session")
def noise_b64():
    """Random noise image that should have no face detected."""
    import numpy as np
    from PIL import Image
    import io
    rng = np.random.default_rng(42)
    arr = rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
