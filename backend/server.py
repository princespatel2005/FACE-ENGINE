"""Smart AI Face Recognition — FastAPI backend.

Modules covered in this single-file service:
- JWT auth (bcrypt) + admin seeding
- Users CRUD with multi-embedding enrollment
- Live recognition (single or multi-frame majority vote)
- Attendance & recognition history logs
- Unknown persons capture
- Dashboard stats
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import bcrypt
import jwt
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field

from face_engine import cosine_similarity, engine
from alerts import create_alert, get_alert_recipient
from cameras import CameraManager
from digest import compose_digest, render_digest_html, scheduler_loop

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"
ACCESS_TTL = timedelta(hours=12)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
MATCH_THRESHOLD = float(os.environ.get("FACE_MATCH_THRESHOLD", "0.42"))
UPLOAD_ROOT = Path(os.environ.get("UPLOAD_ROOT", "/app/backend/uploads"))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
(UPLOAD_ROOT / "users").mkdir(exist_ok=True)
(UPLOAD_ROOT / "unknowns").mkdir(exist_ok=True)
(UPLOAD_ROOT / "cameras").mkdir(exist_ok=True)
KIOSK_UNKNOWN_ALERT_COOLDOWN_S = int(os.environ.get("KIOSK_UNKNOWN_ALERT_COOLDOWN_S", "60"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("faceapp")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Smart AI Face Recognition")

camera_manager = CameraManager(UPLOAD_ROOT / "cameras")
# Cooldown map for unknown alerts per camera → last alert timestamp (isoformat)
_last_unknown_alert_at: dict = {}


# ------------------------------------------------------------------
# Helpers: hashing, tokens
# ------------------------------------------------------------------
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def create_access_token(admin_id: str, email: str, role: str) -> str:
    payload = {
        "sub": admin_id,
        "email": email,
        "role": role,
        "type": "access",
        "exp": datetime.now(timezone.utc) + ACCESS_TTL,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_admin(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        hdr = request.headers.get("Authorization", "")
        if hdr.startswith("Bearer "):
            token = hdr[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    admin = await db.admins.find_one({"id": payload["sub"]})
    if not admin:
        raise HTTPException(401, "Account not found")
    admin.pop("_id", None)
    admin.pop("password_hash", None)
    return admin


def require_role(*roles):
    async def dep(admin=Depends(get_current_admin)):
        if admin["role"] not in roles:
            raise HTTPException(403, f"Requires role: {roles}")
        return admin

    return dep


# ------------------------------------------------------------------
# Pydantic models
# ------------------------------------------------------------------
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AdminOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: str


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    employee_id: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    # Retail additions
    gender: Optional[str] = None                # M | F | Other
    dob: Optional[str] = None                   # ISO date
    address: Optional[str] = None
    notes: Optional[str] = None
    loyalty_points: Optional[int] = 0


class UserOut(UserCreate):
    id: str
    created_at: str
    embeddings_count: int = 0
    thumbnail_url: Optional[str] = None
    watchlist_status: str = "normal"
    total_visits: int = 0
    lifetime_spend: float = 0.0
    last_visit_at: Optional[str] = None


class RegisterFromUnknownIn(BaseModel):
    unknown_id: str
    name: str = Field(min_length=1, max_length=100)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class PurchaseLine(BaseModel):
    product: str
    quantity: float = 1
    price: float = 0
    discount: float = 0


class PurchaseCreate(BaseModel):
    user_id: str
    invoice_number: Optional[str] = None
    items: List[PurchaseLine] = []
    total: float = 0
    payment_mode: Optional[str] = "cash"
    date: Optional[str] = None                  # ISO; defaults to now


class EnrollIn(BaseModel):
    images: List[str]  # data URLs or base64 strings


class WatchlistIn(BaseModel):
    status: str  # normal | vip | blocked


class RecognizeIn(BaseModel):
    image: str
    camera_id: Optional[str] = "webcam"


class MultiFrameIn(BaseModel):
    images: List[str]
    camera_id: Optional[str] = "webcam"


class KioskIn(BaseModel):
    token: str
    images: List[str]
    camera_id: Optional[str] = "kiosk"


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=1)         # rtsp://... or http://...
    type: str = Field(default="rtsp")      # rtsp | ip | usb (usb = frontend only)
    enabled: bool = True


class SettingsIn(BaseModel):
    alert_email: Optional[EmailStr] = None
    kiosk_token: Optional[str] = None


# ------------------------------------------------------------------
# Startup: indexes + admin seed + face engine load
# ------------------------------------------------------------------
async def _on_camera_detections(cam_id: str, cam_name: str, detections: list, annotated_frame):
    """Callback invoked by CameraWorker on every processed frame. Runs identity
    match, logs recognition, sends alerts (unknown / blocked / vip) with cooldown."""
    if not detections:
        return
    # Load gallery once — the manager only calls this every ~1s per camera.
    mat, ids = await _load_gallery()
    umap = await _resolve_users(list(set(ids))) if ids else {}
    recipient = await get_alert_recipient(db)

    for det in detections:
        emb = det.get("embedding")
        if not emb:
            continue
        emb_np = np.asarray(emb, dtype=np.float32)
        uid, sim = _best_match(mat, ids, emb_np)
        if uid and sim >= MATCH_THRESHOLD:
            u = umap.get(uid, {})
            await db.recognition_logs.insert_one({
                "id": str(uuid.uuid4()), "user_id": uid, "camera_id": cam_id,
                "similarity": float(sim), "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            await _log_attendance_if_needed(uid, cam_id, float(sim))
            status = u.get("watchlist_status", "normal")
            if status == "blocked":
                await create_alert(db, "blocked", f"BLOCKED: {u.get('name')} on {cam_name}",
                                   cam_id, user_id=uid, similarity=float(sim),
                                   extra={"name": u.get("name")}, recipient=recipient,
                                   base_url=PUBLIC_BASE_URL)
            elif status == "vip":
                await create_alert(db, "vip", f"VIP arrival: {u.get('name')} on {cam_name}",
                                   cam_id, user_id=uid, similarity=float(sim),
                                   extra={"name": u.get("name")}, recipient=recipient,
                                   base_url=PUBLIC_BASE_URL)
        else:
            # Unknown — throttled alert
            now = datetime.now(timezone.utc)
            last = _last_unknown_alert_at.get(cam_id)
            if last and (now - last).total_seconds() < KIOSK_UNKNOWN_ALERT_COOLDOWN_S:
                continue
            _last_unknown_alert_at[cam_id] = now
            # Save current annotated frame as unknown thumbnail
            unk_id = str(uuid.uuid4())
            filename = f"{unk_id}.jpg"
            path = UPLOAD_ROOT / "unknowns" / filename
            try:
                import cv2 as _cv2
                _cv2.imwrite(str(path), annotated_frame)
            except Exception:
                pass
            await db.unknown_people.insert_one({
                "id": unk_id, "camera_id": cam_id, "similarity": float(sim or 0.0),
                "image_url": f"/uploads/unknowns/{filename}",
                "timestamp": now.isoformat(),
            })
            await create_alert(db, "unknown", f"Unknown face on {cam_name}", cam_id,
                               image_url=f"/uploads/unknowns/{filename}",
                               similarity=float(sim or 0.0), recipient=recipient,
                               base_url=PUBLIC_BASE_URL)


@app.on_event("startup")
async def on_startup():
    await db.admins.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.users.create_index([("name", "text"), ("employee_id", "text"), ("department", "text"), ("phone", "text")])
    await db.embeddings.create_index("user_id")
    await db.attendance_logs.create_index("timestamp")
    await db.recognition_logs.create_index("timestamp")
    await db.unknown_people.create_index("timestamp")
    await db.alerts.create_index("timestamp")
    await db.cameras.create_index("id", unique=True)

    existing = await db.admins.find_one({"email": ADMIN_EMAIL})
    if not existing:
        await db.admins.insert_one({
            "id": str(uuid.uuid4()),
            "email": ADMIN_EMAIL,
            "name": "Administrator",
            "role": "admin",
            "password_hash": hash_password(ADMIN_PASSWORD),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Seeded admin %s", ADMIN_EMAIL)
    elif not verify_password(ADMIN_PASSWORD, existing["password_hash"]):
        await db.admins.update_one(
            {"email": ADMIN_EMAIL},
            {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}},
        )
        logger.info("Refreshed admin password")

    engine.start_background_load()

    # Auto-start enabled cameras
    async def relaunch():
        # Small delay so face engine can warm
        await asyncio.sleep(2)
        async for cam in db.cameras.find({"enabled": True}):
            await camera_manager.add(cam, _on_camera_detections)

    asyncio.create_task(relaunch())
    asyncio.create_task(scheduler_loop(db))


@app.on_event("shutdown")
async def on_shutdown():
    for cid in list(camera_manager.workers.keys()):
        await camera_manager.stop(cid)
    client.close()


# ------------------------------------------------------------------
# Router
# ------------------------------------------------------------------
from fastapi import APIRouter

api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"ok": True, "service": "smart-face-recognition"}


@api.get("/health/engine")
async def engine_health():
    return engine.status()


# ---- Auth ----
@api.post("/auth/login")
async def login(body: LoginIn, response: Response):
    admin = await db.admins.find_one({"email": body.email.lower()})
    if not admin or not verify_password(body.password, admin["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    token = create_access_token(admin["id"], admin["email"], admin["role"])
    response.set_cookie(
        "access_token", token, httponly=True, secure=True, samesite="none",
        max_age=int(ACCESS_TTL.total_seconds()), path="/",
    )
    return {
        "token": token,
        "user": {"id": admin["id"], "email": admin["email"], "name": admin["name"], "role": admin["role"]},
    }


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api.get("/auth/me", response_model=AdminOut)
async def me(admin=Depends(get_current_admin)):
    return AdminOut(**admin)


# ---- Users ----
def _serialize_user(u: dict, embeddings_count: int = 0) -> dict:
    return {
        "id": u["id"],
        "name": u["name"],
        "employee_id": u.get("employee_id"),
        "department": u.get("department"),
        "phone": u.get("phone"),
        "email": u.get("email"),
        "gender": u.get("gender"),
        "dob": u.get("dob"),
        "address": u.get("address"),
        "notes": u.get("notes"),
        "loyalty_points": int(u.get("loyalty_points") or 0),
        "created_at": u["created_at"],
        "embeddings_count": embeddings_count,
        "thumbnail_url": u.get("thumbnail_url"),
        "watchlist_status": u.get("watchlist_status", "normal"),
        "total_visits": int(u.get("total_visits") or 0),
        "lifetime_spend": float(u.get("lifetime_spend") or 0),
        "last_visit_at": u.get("last_visit_at"),
    }


@api.post("/users", response_model=UserOut)
async def create_user(body: UserCreate, admin=Depends(require_role("admin", "operator"))):
    doc = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "employee_id": body.employee_id,
        "department": body.department,
        "phone": body.phone,
        "email": body.email,
        "gender": body.gender,
        "dob": body.dob,
        "address": body.address,
        "notes": body.notes,
        "loyalty_points": body.loyalty_points or 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "thumbnail_url": None,
        "watchlist_status": "normal",
        "total_visits": 0,
        "lifetime_spend": 0.0,
        "last_visit_at": None,
    }
    await db.users.insert_one(doc)
    return UserOut(**_serialize_user(doc, 0))


@api.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: str, body: dict, admin=Depends(require_role("admin", "operator"))):
    allowed = {"name", "employee_id", "department", "phone", "email",
               "gender", "dob", "address", "notes", "loyalty_points"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    r = await db.users.update_one({"id": user_id}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(404, "User not found")
    u = await db.users.find_one({"id": user_id}, {"_id": 0})
    n = await db.embeddings.count_documents({"user_id": user_id})
    return UserOut(**_serialize_user(u, n))


@api.get("/users", response_model=List[UserOut])
async def list_users(search: Optional[str] = None, admin=Depends(get_current_admin)):
    query = {}
    if search:
        rex = {"$regex": search, "$options": "i"}
        query = {"$or": [{"name": rex}, {"employee_id": rex}, {"department": rex}, {"phone": rex}]}
    users = await db.users.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    counts = {}
    if users:
        ids = [u["id"] for u in users]
        pipe = [{"$match": {"user_id": {"$in": ids}}}, {"$group": {"_id": "$user_id", "n": {"$sum": 1}}}]
        async for row in db.embeddings.aggregate(pipe):
            counts[row["_id"]] = row["n"]
    return [UserOut(**_serialize_user(u, counts.get(u["id"], 0))) for u in users]


@api.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: str, admin=Depends(get_current_admin)):
    u = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(404, "User not found")
    n = await db.embeddings.count_documents({"user_id": user_id})
    return UserOut(**_serialize_user(u, n))


@api.delete("/users/{user_id}")
async def delete_user(user_id: str, admin=Depends(require_role("admin"))):
    r = await db.users.delete_one({"id": user_id})
    await db.embeddings.delete_many({"user_id": user_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "User not found")
    return {"ok": True}


@api.patch("/users/{user_id}/watchlist", response_model=UserOut)
async def set_watchlist(user_id: str, body: WatchlistIn, admin=Depends(require_role("admin", "operator"))):
    if body.status not in ("normal", "vip", "blocked"):
        raise HTTPException(400, "status must be normal | vip | blocked")
    r = await db.users.update_one({"id": user_id}, {"$set": {"watchlist_status": body.status}})
    if r.matched_count == 0:
        raise HTTPException(404, "User not found")
    u = await db.users.find_one({"id": user_id}, {"_id": 0})
    n = await db.embeddings.count_documents({"user_id": user_id})
    return UserOut(**_serialize_user(u, n))


@api.post("/users/{user_id}/enroll")
async def enroll(user_id: str, body: EnrollIn, admin=Depends(require_role("admin", "operator"))):
    if not engine.status()["ready"]:
        raise HTTPException(503, f"Face engine not ready: {engine.status().get('error') or 'still loading'}")
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(404, "User not found")

    saved = 0
    rejected = []
    thumbnail_saved = False

    for idx, img_b64 in enumerate(body.images):
        try:
            img = engine.decode_base64_image(img_b64)
        except Exception:
            rejected.append({"index": idx, "reason": "Invalid image data"})
            continue
        dets = engine.analyze(img)
        if not dets:
            rejected.append({"index": idx, "reason": "No face detected"})
            continue
        det = max(dets, key=lambda d: (d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1]))
        q = engine.quality_check(img, det.bbox)
        if q:
            rejected.append({"index": idx, "reason": q})
            continue

        await db.embeddings.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "embedding": det.embedding.tolist(),
            "det_score": det.det_score,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        saved += 1

        # Persist first accepted frame as thumbnail
        if not thumbnail_saved:
            filename = f"{user_id}.jpg"
            path = UPLOAD_ROOT / "users" / filename
            b64 = img_b64.split(",", 1)[1] if img_b64.startswith("data:") else img_b64
            path.write_bytes(base64.b64decode(b64))
            await db.users.update_one({"id": user_id}, {"$set": {"thumbnail_url": f"/uploads/users/{filename}"}})
            thumbnail_saved = True

    total = await db.embeddings.count_documents({"user_id": user_id})
    return {"saved": saved, "total_embeddings": total, "rejected": rejected}


# ---- Recognition ----
async def _load_gallery():
    """Load all embeddings + user index into memory for fast cosine matching."""
    rows = await db.embeddings.find({}, {"_id": 0}).to_list(200000)
    if not rows:
        return None, []
    mat = np.array([r["embedding"] for r in rows], dtype=np.float32)
    ids = [r["user_id"] for r in rows]
    return mat, ids


async def _resolve_users(ids):
    users = await db.users.find({"id": {"$in": list(set(ids))}}, {"_id": 0}).to_list(len(ids))
    return {u["id"]: u for u in users}


def _best_match(mat, ids, embedding: np.ndarray):
    if mat is None:
        return None, 0.0
    sims = mat @ embedding.astype(np.float32)  # both L2 normalized
    j = int(np.argmax(sims))
    return ids[j], float(sims[j])


async def _log_attendance_if_needed(user_id: str, camera_id: str, similarity: float):
    """Create attendance record once per user per calendar day. Also increments
    user.total_visits + updates last_visit_at (retail semantics)."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    existing = await db.attendance_logs.find_one({"user_id": user_id, "timestamp": {"$gte": start_of_day}})
    if existing:
        return False
    await db.attendance_logs.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "camera_id": camera_id,
        "similarity": similarity,
        "timestamp": now.isoformat(),
    })
    await db.users.update_one(
        {"id": user_id},
        {"$inc": {"total_visits": 1}, "$set": {"last_visit_at": now.isoformat()}},
    )
    return True


async def _save_unknown(img_b64: str, camera_id: str, similarity: float):
    uid = str(uuid.uuid4())
    filename = f"{uid}.jpg"
    b64 = img_b64.split(",", 1)[1] if img_b64.startswith("data:") else img_b64
    (UPLOAD_ROOT / "unknowns" / filename).write_bytes(base64.b64decode(b64))
    await db.unknown_people.insert_one({
        "id": uid,
        "camera_id": camera_id,
        "similarity": similarity,
        "image_url": f"/uploads/unknowns/{filename}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return uid


@api.post("/recognize")
async def recognize(body: RecognizeIn, admin=Depends(get_current_admin)):
    if not engine.status()["ready"]:
        raise HTTPException(503, f"Face engine not ready: {engine.status().get('error') or 'loading'}")
    started = datetime.now(timezone.utc)
    img = engine.decode_base64_image(body.image)
    dets = engine.analyze(img)
    mat, ids = await _load_gallery()

    results = []
    for det in dets:
        q = engine.quality_check(img, det.bbox)
        if q:
            results.append({"bbox": det.bbox, "status": "low_quality", "message": q})
            continue
        uid, sim = _best_match(mat, ids, det.embedding)
        if uid and sim >= MATCH_THRESHOLD:
            umap = await _resolve_users([uid])
            u = umap.get(uid, {})
            results.append({
                "bbox": det.bbox, "status": "known", "user_id": uid,
                "name": u.get("name", "Unknown"), "employee_id": u.get("employee_id"),
                "department": u.get("department"), "similarity": round(sim, 4),
                "thumbnail_url": u.get("thumbnail_url"),
                "watchlist_status": u.get("watchlist_status", "normal"),
            })
            await db.recognition_logs.insert_one({
                "id": str(uuid.uuid4()), "user_id": uid, "camera_id": body.camera_id,
                "similarity": sim, "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        else:
            results.append({"bbox": det.bbox, "status": "unknown", "similarity": round(sim, 4)})

    elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    return {"detections": results, "elapsed_ms": elapsed_ms}


@api.post("/recognize/multi")
async def recognize_multi(body: MultiFrameIn, admin=Depends(get_current_admin)):
    """Multi-frame recognition: capture N frames, majority vote for stable identity."""
    if not engine.status()["ready"]:
        raise HTTPException(503, f"Face engine not ready: {engine.status().get('error') or 'loading'}")
    if not body.images:
        raise HTTPException(400, "images required")
    started = datetime.now(timezone.utc)
    mat, ids = await _load_gallery()
    votes: List[tuple] = []  # (user_id or None, similarity)
    best_frame_b64 = None

    for img_b64 in body.images:
        try:
            img = engine.decode_base64_image(img_b64)
        except Exception:
            continue
        dets = engine.analyze(img)
        if not dets:
            continue
        det = max(dets, key=lambda d: (d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1]))
        q = engine.quality_check(img, det.bbox)
        if q:
            continue
        uid, sim = _best_match(mat, ids, det.embedding)
        if uid and sim >= MATCH_THRESHOLD:
            votes.append((uid, sim))
        else:
            votes.append((None, sim))
        if best_frame_b64 is None:
            best_frame_b64 = img_b64

    if not votes:
        return {"status": "no_face", "message": "No usable frames captured.", "frames": len(body.images)}

    counter = Counter([v[0] for v in votes])
    top_id, top_count = counter.most_common(1)[0]
    ratio = top_count / len(votes)

    if top_id is not None and ratio >= 0.4:
        sims = [s for u, s in votes if u == top_id]
        avg = float(np.mean(sims))
        umap = await _resolve_users([top_id])
        u = umap.get(top_id, {})
        watchlist_status = u.get("watchlist_status", "normal")
        await db.recognition_logs.insert_one({
            "id": str(uuid.uuid4()), "user_id": top_id, "camera_id": body.camera_id,
            "similarity": avg, "timestamp": datetime.now(timezone.utc).isoformat(),
            "frames": len(body.images), "votes": top_count,
        })
        new_attendance = await _log_attendance_if_needed(top_id, body.camera_id, avg)
        recipient = await get_alert_recipient(db)
        if watchlist_status == "blocked":
            await create_alert(db, "blocked", f"BLOCKED: {u.get('name')}", body.camera_id,
                               user_id=top_id, similarity=avg,
                               extra={"name": u.get("name")}, recipient=recipient,
                               base_url=PUBLIC_BASE_URL)
        elif watchlist_status == "vip":
            await create_alert(db, "vip", f"VIP: {u.get('name')}", body.camera_id,
                               user_id=top_id, similarity=avg,
                               extra={"name": u.get("name")}, recipient=recipient,
                               base_url=PUBLIC_BASE_URL)
        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {
            "status": "known", "user_id": top_id, "name": u.get("name"),
            "employee_id": u.get("employee_id"), "department": u.get("department"),
            "thumbnail_url": u.get("thumbnail_url"), "similarity": round(avg, 4),
            "watchlist_status": watchlist_status,
            "votes": top_count, "frames": len(body.images), "attendance_logged": new_attendance,
            "elapsed_ms": elapsed_ms,
        }

    # Unknown — save best frame + alert
    unk_id = None
    best_sim = max((s for _, s in votes), default=0.0)
    if best_frame_b64 is not None:
        unk_id = await _save_unknown(best_frame_b64, body.camera_id, best_sim)
    recipient = await get_alert_recipient(db)
    await create_alert(db, "unknown", "Unknown face detected", body.camera_id,
                       image_url=f"/uploads/unknowns/{unk_id}.jpg" if unk_id else None,
                       similarity=float(best_sim), recipient=recipient,
                       base_url=PUBLIC_BASE_URL)
    elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    return {"status": "unknown", "unknown_id": unk_id, "frames": len(body.images), "elapsed_ms": elapsed_ms}


# ---- Attendance ----
@api.get("/attendance")
async def list_attendance(limit: int = 200, admin=Depends(get_current_admin)):
    rows = await db.attendance_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    umap = await _resolve_users([r["user_id"] for r in rows])
    for r in rows:
        u = umap.get(r["user_id"], {})
        r["name"] = u.get("name", "Unknown")
        r["employee_id"] = u.get("employee_id")
        r["department"] = u.get("department")
        r["thumbnail_url"] = u.get("thumbnail_url")
    return rows


# ---- Recognition history ----
@api.get("/recognition-history")
async def list_history(limit: int = 200, admin=Depends(get_current_admin)):
    rows = await db.recognition_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    umap = await _resolve_users([r["user_id"] for r in rows])
    for r in rows:
        u = umap.get(r["user_id"], {})
        r["name"] = u.get("name", "Unknown")
        r["employee_id"] = u.get("employee_id")
        r["thumbnail_url"] = u.get("thumbnail_url")
    return rows


# ---- Unknowns ----
@api.get("/unknowns")
async def list_unknowns(limit: int = 200, admin=Depends(get_current_admin)):
    return await db.unknown_people.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)


@api.delete("/unknowns/{unk_id}")
async def delete_unknown(unk_id: str, admin=Depends(require_role("admin", "operator"))):
    r = await db.unknown_people.find_one({"id": unk_id})
    if not r:
        raise HTTPException(404, "Not found")
    await db.unknown_people.delete_one({"id": unk_id})
    # Best effort remove file
    try:
        path = UPLOAD_ROOT / r["image_url"].lstrip("/").replace("uploads/", "", 1)
        if path.exists():
            path.unlink()
    except Exception:
        pass
    return {"ok": True}


# ---- Dashboard ----
@api.get("/dashboard/stats")
async def stats(admin=Depends(get_current_admin)):
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    total_users = await db.users.count_documents({})
    today_att = await db.attendance_logs.count_documents({"timestamp": {"$gte": start_of_day}})
    total_unknown = await db.unknown_people.count_documents({})
    total_recognitions = await db.recognition_logs.count_documents({})

    # Weekly attendance (last 7 days)
    week = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        n = await db.attendance_logs.count_documents(
            {"timestamp": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}}
        )
        week.append({"day": day_start.strftime("%a"), "count": n})

    # Avg similarity of recent recognitions
    recent = await db.recognition_logs.find({}, {"similarity": 1, "_id": 0}).sort("timestamp", -1).to_list(200)
    avg_sim = float(np.mean([r["similarity"] for r in recent])) if recent else 0.0

    return {
        "total_users": total_users,
        "today_attendance": today_att,
        "total_unknown": total_unknown,
        "total_recognitions": total_recognitions,
        "engine": engine.status(),
        "weekly_attendance": week,
        "avg_similarity": round(avg_sim, 4),
        "match_threshold": MATCH_THRESHOLD,
        "cameras_total": await db.cameras.count_documents({}),
        "cameras_online": sum(1 for w in camera_manager.workers.values() if w.status.get("state") == "running"),
        "unread_alerts": await db.alerts.count_documents({"read": False}),
    }


# ---- Cameras ----
@api.get("/cameras")
async def list_cameras(admin=Depends(get_current_admin)):
    rows = await db.cameras.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    for r in rows:
        r["status"] = camera_manager.status(r["id"]).get("state", "stopped")
        r["fps"] = camera_manager.status(r["id"]).get("fps", 0)
        r["last_frame_at"] = camera_manager.status(r["id"]).get("last_frame_at")
        r["error"] = camera_manager.status(r["id"]).get("error")
    return rows


@api.post("/cameras")
async def create_camera(body: CameraCreate, admin=Depends(require_role("admin", "operator"))):
    doc = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "url": body.url,
        "type": body.type,
        "enabled": body.enabled,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.cameras.insert_one(doc)
    if body.enabled and body.type != "usb":
        await camera_manager.add(doc, _on_camera_detections)
    doc.pop("_id", None)
    doc["status"] = camera_manager.status(doc["id"]).get("state", "stopped")
    return doc


@api.patch("/cameras/{cam_id}")
async def update_camera(cam_id: str, body: dict, admin=Depends(require_role("admin", "operator"))):
    updates = {k: v for k, v in body.items() if k in ("name", "url", "enabled")}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    r = await db.cameras.update_one({"id": cam_id}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(404, "Camera not found")
    cam = await db.cameras.find_one({"id": cam_id}, {"_id": 0})
    # Restart worker with new settings
    await camera_manager.stop(cam_id)
    if cam.get("enabled") and cam.get("type") != "usb":
        await camera_manager.add(cam, _on_camera_detections)
    return cam


@api.delete("/cameras/{cam_id}")
async def delete_camera(cam_id: str, admin=Depends(require_role("admin"))):
    await camera_manager.stop(cam_id)
    r = await db.cameras.delete_one({"id": cam_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Camera not found")
    return {"ok": True}


@api.get("/cameras/{cam_id}/status")
async def camera_status(cam_id: str, admin=Depends(get_current_admin)):
    return camera_manager.status(cam_id)


# ---- Alerts ----
@api.get("/alerts")
async def list_alerts(limit: int = 50, since: Optional[str] = None, admin=Depends(get_current_admin)):
    q = {}
    if since:
        q["timestamp"] = {"$gt": since}
    return await db.alerts.find(q, {"_id": 0}).sort("timestamp", -1).to_list(limit)


@api.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: str, admin=Depends(get_current_admin)):
    r = await db.alerts.update_one({"id": alert_id}, {"$set": {"read": True}})
    if r.matched_count == 0:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@api.post("/alerts/read-all")
async def mark_all_read(admin=Depends(get_current_admin)):
    await db.alerts.update_many({"read": False}, {"$set": {"read": True}})
    return {"ok": True}


# ---- Settings (notifications + kiosk token) ----
@api.get("/settings")
async def get_settings(admin=Depends(get_current_admin)):
    s = await db.settings.find_one({"_id": "notifications"})
    if not s:
        return {"alert_email": os.environ.get("ALERT_TO", ""), "kiosk_token": ""}
    return {
        "alert_email": s.get("alert_email", ""),
        "kiosk_token": s.get("kiosk_token", ""),
    }


@api.patch("/settings")
async def update_settings(body: SettingsIn, admin=Depends(require_role("admin"))):
    updates = {}
    if body.alert_email is not None:
        updates["alert_email"] = body.alert_email
    if body.kiosk_token is not None:
        updates["kiosk_token"] = body.kiosk_token
    if not updates:
        return {"ok": True}
    await db.settings.update_one({"_id": "notifications"}, {"$set": updates}, upsert=True)
    return {"ok": True, **updates}


@api.post("/settings/test-email")
async def send_test_email(admin=Depends(require_role("admin"))):
    recipient = await get_alert_recipient(db)
    if not recipient:
        raise HTTPException(400, "No alert_email configured. Add one in Settings first.")
    from alerts import send_email as _send
    email_id = await _send(recipient, "Sentinel FR — test alert",
                           "<p>If you can read this, Resend delivery is working. 🎯</p>")
    if not email_id:
        raise HTTPException(502, "Resend rejected the send. Check API key & recipient (sandbox only sends to Resend account owner).")
    return {"ok": True, "email_id": email_id, "recipient": recipient}


# ---- Kiosk ----
# ---- Register from unknown (retail workflow) ----
@api.post("/register-from-unknown", response_model=UserOut)
async def register_from_unknown(body: RegisterFromUnknownIn, admin=Depends(require_role("admin", "operator"))):
    """Convert an unknown-face capture into a full customer.
    Reuses the saved unknown image + generates an embedding from it."""
    unk = await db.unknown_people.find_one({"id": body.unknown_id})
    if not unk:
        raise HTTPException(404, "Unknown record not found")
    if not engine.status()["ready"]:
        raise HTTPException(503, "Face engine not ready")

    # Locate source file
    from pathlib import Path as _P
    src = _P(UPLOAD_ROOT) / unk["image_url"].lstrip("/").replace("uploads/", "", 1)
    if not src.exists():
        raise HTTPException(410, "Unknown image no longer available")
    import cv2 as _cv2
    img = _cv2.imread(str(src))
    if img is None:
        raise HTTPException(500, "Cannot decode unknown image")
    dets = engine.analyze(img)
    if not dets:
        raise HTTPException(422, "No face detected on that capture — try a different unknown.")
    det = max(dets, key=lambda d: (d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1]))

    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id, "name": body.name, "phone": body.phone, "email": body.email,
        "gender": body.gender, "address": body.address, "notes": body.notes,
        "employee_id": None, "department": None, "dob": None, "loyalty_points": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "thumbnail_url": f"/uploads/users/{user_id}.jpg",
        "watchlist_status": "normal",
        "total_visits": 0, "lifetime_spend": 0.0, "last_visit_at": None,
    }
    await db.users.insert_one(doc)

    # Save embedding + copy image as user thumbnail
    await db.embeddings.insert_one({
        "id": str(uuid.uuid4()), "user_id": user_id,
        "embedding": det.embedding.tolist(), "det_score": det.det_score,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    dst = _P(UPLOAD_ROOT) / "users" / f"{user_id}.jpg"
    dst.write_bytes(src.read_bytes())

    # Delete the unknown record (customer is now known)
    await db.unknown_people.delete_one({"id": body.unknown_id})

    return UserOut(**_serialize_user(doc, 1))


# ---- Purchases ----
@api.get("/purchases")
async def list_purchases(user_id: Optional[str] = None, limit: int = 100,
                         admin=Depends(get_current_admin)):
    q = {"user_id": user_id} if user_id else {}
    rows = await db.purchases.find(q, {"_id": 0}).sort("date", -1).to_list(limit)
    if not user_id:
        umap = await _resolve_users([r["user_id"] for r in rows])
        for r in rows:
            u = umap.get(r["user_id"], {})
            r["customer_name"] = u.get("name", "Unknown")
    return rows


@api.post("/purchases")
async def create_purchase(body: PurchaseCreate, admin=Depends(require_role("admin", "operator"))):
    u = await db.users.find_one({"id": body.user_id})
    if not u:
        raise HTTPException(404, "User not found")
    total = float(body.total) if body.total else sum((li.price * li.quantity - li.discount) for li in body.items)
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": body.user_id,
        "invoice_number": body.invoice_number or f"INV-{int(datetime.now(timezone.utc).timestamp())}",
        "items": [li.model_dump() for li in body.items],
        "total": float(total),
        "payment_mode": body.payment_mode or "cash",
        "date": body.date or datetime.now(timezone.utc).isoformat(),
    }
    await db.purchases.insert_one(doc)
    await db.users.update_one(
        {"id": body.user_id},
        {"$inc": {"lifetime_spend": total, "loyalty_points": int(total // 10)}},
    )
    doc.pop("_id", None)
    return doc


@api.delete("/purchases/{purchase_id}")
async def delete_purchase(purchase_id: str, admin=Depends(require_role("admin"))):
    r = await db.purchases.find_one({"id": purchase_id})
    if not r:
        raise HTTPException(404, "Not found")
    await db.purchases.delete_one({"id": purchase_id})
    await db.users.update_one(
        {"id": r["user_id"]},
        {"$inc": {"lifetime_spend": -float(r.get("total", 0)), "loyalty_points": -int(float(r.get("total", 0)) // 10)}},
    )
    return {"ok": True}


# ---- Reports ----
@api.get("/reports/overview")
async def report_overview(days: int = 7, admin=Depends(get_current_admin)):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).isoformat()
    total_visits = await db.attendance_logs.count_documents({"timestamp": {"$gte": start}})
    unique = len(await db.attendance_logs.distinct("user_id", {"timestamp": {"$gte": start}}))
    unknown = await db.unknown_people.count_documents({"timestamp": {"$gte": start}})
    vip_ids = [u["id"] async for u in db.users.find({"watchlist_status": "vip"}, {"id": 1})]
    vip_visits = await db.attendance_logs.count_documents(
        {"user_id": {"$in": vip_ids}, "timestamp": {"$gte": start}}
    ) if vip_ids else 0

    # Peak hour histogram
    pipe = [
        {"$match": {"timestamp": {"$gte": start}}},
        {"$project": {"hour": {"$hour": {"$dateFromString": {"dateString": "$timestamp"}}}}},
        {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    peak = await db.attendance_logs.aggregate(pipe).to_list(24)
    peak_hours = [{"hour": r["_id"], "count": r["count"]} for r in peak]

    return {
        "days": days,
        "total_visits": total_visits,
        "unique_visitors": unique,
        "unknown": unknown,
        "vip_visits": vip_visits,
        "peak_hours": peak_hours,
    }


@api.get("/reports/top-spenders")
async def report_top_spenders(limit: int = 10, admin=Depends(get_current_admin)):
    rows = await db.users.find({"lifetime_spend": {"$gt": 0}}, {"_id": 0}).sort("lifetime_spend", -1).limit(limit).to_list(limit)
    return [_serialize_user(u) for u in rows]


@api.get("/reports/frequent-visitors")
async def report_frequent_visitors(days: int = 30, limit: int = 10, admin=Depends(get_current_admin)):
    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    pipe = [
        {"$match": {"timestamp": {"$gte": start}}},
        {"$group": {"_id": "$user_id", "visits": {"$sum": 1}, "last": {"$max": "$timestamp"}}},
        {"$sort": {"visits": -1}},
        {"$limit": limit},
    ]
    rows = await db.attendance_logs.aggregate(pipe).to_list(limit)
    ids = [r["_id"] for r in rows]
    umap = await _resolve_users(ids)
    return [
        {**_serialize_user(umap.get(r["_id"], {"id": r["_id"], "name": "Unknown", "created_at": ""})),
         "recent_visits": r["visits"], "most_recent_at": r["last"]}
        for r in rows if umap.get(r["_id"])
    ]


@api.get("/reports/vips")
async def report_vips(admin=Depends(get_current_admin)):
    rows = await db.users.find({"watchlist_status": "vip"}, {"_id": 0}).sort("lifetime_spend", -1).to_list(100)
    return [_serialize_user(u) for u in rows]


@api.post("/reports/send-digest")
async def send_digest_now(admin=Depends(require_role("admin"))):
    recipient = await get_alert_recipient(db)
    if not recipient:
        raise HTTPException(400, "Set alert_email in Settings first.")
    data = await compose_digest(db)
    html = render_digest_html(data)
    from alerts import send_email as _send
    email_id = await _send(recipient, f"Sentinel FR Weekly Digest ({data['period_start']} – {data['period_end']})", html)
    if not email_id:
        raise HTTPException(502, "Resend rejected the send. Sandbox only sends to Resend account owner.")
    await db.settings.update_one({"_id": "notifications"}, {"$set": {"last_digest_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return {"ok": True, "email_id": email_id, "recipient": recipient, "data": data}


@api.post("/kiosk/verify")
async def kiosk_verify(body: KioskIn):
    """Public endpoint (no auth) — validated by kiosk_token stored in settings."""
    s = await db.settings.find_one({"_id": "notifications"})
    if not s or not s.get("kiosk_token") or s["kiosk_token"] != body.token:
        raise HTTPException(401, "Invalid kiosk token")
    if not engine.status()["ready"]:
        raise HTTPException(503, "Face engine not ready")
    if not body.images:
        raise HTTPException(400, "images required")

    mat, ids = await _load_gallery()
    votes = []
    best_frame_b64 = None
    for img_b64 in body.images:
        try:
            img = engine.decode_base64_image(img_b64)
        except Exception:
            continue
        dets = engine.analyze(img)
        if not dets:
            continue
        det = max(dets, key=lambda d: (d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1]))
        q = engine.quality_check(img, det.bbox)
        if q:
            continue
        uid, sim = _best_match(mat, ids, det.embedding)
        votes.append((uid if sim >= MATCH_THRESHOLD else None, sim))
        if best_frame_b64 is None:
            best_frame_b64 = img_b64

    if not votes:
        return {"status": "no_face"}

    counter = Counter([v[0] for v in votes])
    top_id, top_count = counter.most_common(1)[0]
    if top_id and top_count / len(votes) >= 0.4:
        sims = [s for u, s in votes if u == top_id]
        avg = float(np.mean(sims))
        umap = await _resolve_users([top_id])
        u = umap.get(top_id, {})
        await db.recognition_logs.insert_one({
            "id": str(uuid.uuid4()), "user_id": top_id, "camera_id": body.camera_id,
            "similarity": avg, "timestamp": datetime.now(timezone.utc).isoformat(),
            "frames": len(body.images), "votes": top_count, "kiosk": True,
        })
        new_att = await _log_attendance_if_needed(top_id, body.camera_id, avg)
        return {
            "status": "known", "name": u.get("name"), "employee_id": u.get("employee_id"),
            "department": u.get("department"), "thumbnail_url": u.get("thumbnail_url"),
            "similarity": round(avg, 4), "watchlist_status": u.get("watchlist_status", "normal"),
            "attendance_logged": new_att,
        }

    if best_frame_b64:
        best_sim = max((s for _, s in votes), default=0.0)
        await _save_unknown(best_frame_b64, body.camera_id, best_sim)
        recipient = await get_alert_recipient(db)
        await create_alert(db, "unknown", f"Kiosk unknown on {body.camera_id}",
                           body.camera_id, similarity=float(best_sim),
                           recipient=recipient, base_url=PUBLIC_BASE_URL)
    return {"status": "unknown"}


# ------------------------------------------------------------------
# Mount routers & middleware
# ------------------------------------------------------------------
app.include_router(api)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_ROOT)), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
