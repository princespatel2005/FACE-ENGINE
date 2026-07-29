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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("faceapp")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Smart AI Face Recognition")


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


class UserOut(UserCreate):
    id: str
    created_at: str
    embeddings_count: int = 0
    thumbnail_url: Optional[str] = None


class EnrollIn(BaseModel):
    images: List[str]  # data URLs or base64 strings


class RecognizeIn(BaseModel):
    image: str
    camera_id: Optional[str] = "webcam"


class MultiFrameIn(BaseModel):
    images: List[str]
    camera_id: Optional[str] = "webcam"


# ------------------------------------------------------------------
# Startup: indexes + admin seed + face engine load
# ------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    await db.admins.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.users.create_index([("name", "text"), ("employee_id", "text"), ("department", "text"), ("phone", "text")])
    await db.embeddings.create_index("user_id")
    await db.attendance_logs.create_index("timestamp")
    await db.recognition_logs.create_index("timestamp")
    await db.unknown_people.create_index("timestamp")

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


@app.on_event("shutdown")
async def on_shutdown():
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
        "created_at": u["created_at"],
        "embeddings_count": embeddings_count,
        "thumbnail_url": u.get("thumbnail_url"),
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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "thumbnail_url": None,
    }
    await db.users.insert_one(doc)
    return UserOut(**_serialize_user(doc, 0))


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
    """Create attendance record once per user per calendar day."""
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
        await db.recognition_logs.insert_one({
            "id": str(uuid.uuid4()), "user_id": top_id, "camera_id": body.camera_id,
            "similarity": avg, "timestamp": datetime.now(timezone.utc).isoformat(),
            "frames": len(body.images), "votes": top_count,
        })
        new_attendance = await _log_attendance_if_needed(top_id, body.camera_id, avg)
        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {
            "status": "known", "user_id": top_id, "name": u.get("name"),
            "employee_id": u.get("employee_id"), "department": u.get("department"),
            "thumbnail_url": u.get("thumbnail_url"), "similarity": round(avg, 4),
            "votes": top_count, "frames": len(body.images), "attendance_logged": new_attendance,
            "elapsed_ms": elapsed_ms,
        }

    # Unknown — save best frame
    unk_id = None
    if best_frame_b64 is not None:
        best_sim = max((s for _, s in votes), default=0.0)
        unk_id = await _save_unknown(best_frame_b64, body.camera_id, best_sim)
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
    }


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
