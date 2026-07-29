# Smart AI Face Recognition — PRD

## Original Problem
Build a production-ready AI Face Recognition Web Application (Sentinel FR). Real-time recognition via webcam/IP camera. If face is known, display details + confidence + attendance/log; if unknown, save the face, timestamp, camera, and store for review. Uses SCRFD detection + ArcFace embeddings (via InsightFace's buffalo_l — closest open-source equivalent to AdaFace), cosine similarity, multi-frame verification (15 frames + majority vote), multi-pose enrollment (~50 shots across 7 poses), quality gating. Pages: Login, Dashboard, Live Recognition, Register, Users, Attendance, History, Unknown Persons.

## User Choices (from ask_human)
- Database: **MongoDB**
- Frontend: React + JS + Tailwind + Shadcn (existing template)
- AI: **InsightFace buffalo_l** (SCRFD + w600k_r50 ArcFace) CPU ONNX
- Scope: MVP = Login, Dashboard, Live Recognition, Register, Users, Attendance, History, Unknown Persons
- Notifications: deferred

## Architecture
- Backend: FastAPI + Motor (MongoDB) + JWT auth (bcrypt) + InsightFace + OpenCV
- Frontend: React (CRA) + Tailwind + Shadcn + Recharts + Sonner + Phosphor Icons
- Storage: local `/app/backend/uploads/{users,unknowns}` served via `/uploads` static mount
- Face model auto-downloaded on first startup (~281MB) then cached in `/root/.insightface/models/`

## Implemented (2026-07-29)
- ✅ JWT login/logout/me with admin seed (admin@example.com / admin123)
- ✅ Users CRUD + text search (name/employee_id/department/phone)
- ✅ Multi-pose enrollment endpoint with per-frame quality checks (blur/brightness/size/margin)
- ✅ Single-frame `/api/recognize` with per-face bbox + status (known/unknown/low_quality) and inline recognition logs
- ✅ Multi-frame `/api/recognize/multi` with 15-frame majority vote, attendance auto-log (once/day/user), unknown face capture
- ✅ Dashboard stats: enrolled count, today's attendance, unknowns, alerts, cameras online, engine, weekly chart
- ✅ Frontend: dark security-command-center UI (Chivo/JetBrains Mono), sidebar layout, live camera preview with color-coded bounding boxes and live label, 7-pose enrollment wizard
- ✅ 30/30 backend pytest cases passing (real InsightFace embeddings, self-match, majority voting, unknown flow, 401 gating)

## Iteration 2 (2026-07-29)
- ✅ **RTSP / IP Cameras**: `CameraManager` + per-camera `CameraWorker` asyncio task reads OpenCV `VideoCapture` every ~1s, runs recognition, saves annotated JPEG, triggers alerts. Endpoints: `GET/POST/PATCH/DELETE /api/cameras`, `GET /api/cameras/{id}/status`, snapshot served at `/uploads/cameras/{id}.jpg`. Frontend Cameras page with add/enable/disable/delete + live snapshot grid.
- ✅ **Unknown / VIP / Blocked Alerts**: `alerts.py` sends via Resend (`resend>=2.0.0`) with rich HTML templates + stores alert docs in Mongo. `/api/alerts`, `/api/alerts/{id}/read`, `/api/alerts/read-all`. Frontend polls every 4s and fires sonner toasts + browser Notification API notifications.
- ✅ **Watchlist Boost**: users have `watchlist_status` (normal | vip | blocked). `PATCH /api/users/{id}/watchlist`. Live Recognition + Kiosk color-code bounding boxes and result cards (gold VIP, red blocked). Recognize/multi returns `watchlist_status` and creates matching alert.
- ✅ **Kiosk Mode**: public `/kiosk?token=...` page, no login required. `POST /api/kiosk/verify` gated by kiosk_token stored in settings. Auto-loops 12-frame verification every 6.5s. Settings page has token generator + shareable URL.
- ✅ 63/63 backend pytest cases passing (30 original + 33 new for iteration 2).

## Deferred / Backlog (P1)
- Camera Management page (RTSP/IP camera streams beyond USB webcam)
- Settings + full Admin Panel UI (users/roles CRUD)
- RBAC UI (Admin/Operator/Viewer role picker + creation)
- Email + Telegram + browser push notifications for unknown-person alerts
- Docker Compose + NGINX deployment configs
- Real-time WebSocket stream (currently we poll `/api/recognize` every 900ms)
- FAISS index once user count > ~10k

## Test Credentials
See `/app/memory/test_credentials.md`.
