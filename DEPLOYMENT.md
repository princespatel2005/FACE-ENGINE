# Smart AI Face Recognition — Local Setup & Render Deployment Guide

This guide explains how to configure environment variables, run the application locally, and deploy it to Render.

---

## 📁 Environment Variables Overview

All environment variable templates are provided in `.env.example` and `.example.env`.

### 🔑 Required & Optional Variables Matrix

| Variable | Description | Local Default | Production / Render | Required? |
|---|---|---|---|---|
| `PORT` | Backend HTTP server port | `8000` | Automatically set by Render (`$PORT`) | Optional |
| `MONGO_URL` | MongoDB connection URI | `mongodb://localhost:27017` | `mongodb+srv://user:pass@cluster.mongodb.net/` | **Yes** |
| `DB_NAME` | Database name | `sentinel_fr` | `sentinel_fr` | **Yes** |
| `JWT_SECRET` | Secret key for JWT auth tokens | `dev-jwt-secret-key-change-in-production-12345` | Auto-generated or strong random secret | Optional (Recommended) |
| `ADMIN_EMAIL` | Default admin email created on initial seed | `admin@example.com` | `admin@yourdomain.com` | Optional |
| `ADMIN_PASSWORD` | Default admin password | `admin123` | Secure password | Optional |
| `FACE_MATCH_THRESHOLD` | Recognition similarity threshold | `0.42` | `0.42` | Optional |
| `UPLOAD_ROOT` | Storage directory for user photos & snapshots | `./uploads` | `./uploads` or Mounted Disk | Optional |
| `CORS_ORIGINS` | Allowed frontend origins | `http://localhost:3000,http://localhost:8000` | `https://your-frontend.onrender.com` | Optional |
| `REACT_APP_BACKEND_URL` | Frontend API client target URL | `http://localhost:8000` | `https://your-backend.onrender.com` | **Yes** (for Frontend) |
| `RESEND_API_KEY` | Resend API key for email alerts | *(Empty)* | `re_123...` | Optional |
| `SENDER_EMAIL` | Sender address for email alerts | `onboarding@resend.dev` | `alerts@yourdomain.com` | Optional |
| `ALERT_TO` | Default notification recipient email | *(Empty)* | `security@yourdomain.com` | Optional |

---

## 💻 1. Running Locally (Step-by-Step)

### Prerequisites:
- Python 3.9+
- Node.js 18+ and Yarn / npm
- MongoDB (Running locally on `localhost:27017` OR a free MongoDB Atlas cloud cluster)

### Step 1: Clone & Configure `.env`
1. Copy `.env.example` to `.env` in the root folder:
   ```bash
   cp .env.example .env
   ```
2. Verify that `MONGO_URL=mongodb://localhost:27017` (or your MongoDB Atlas connection string).

### Step 2: Start the Backend
1. Open a terminal in `backend/`:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
2. Start the server:
   ```bash
   python server.py
   # Or using uvicorn directly:
   uvicorn server:app --reload --port 8000
   ```
   The backend API will be live at `http://localhost:8000`.

### Step 3: Start the Frontend
1. Open a new terminal in `frontend/`:
   ```bash
   cd frontend
   npm install
   ```
2. Start the React dev server:
   ```bash
   npm start
   ```
   The web application will open automatically at `http://localhost:3000`.

---

## 🚀 2. Deploying to Render (Step-by-Step)

### Option A: 1-Click Blueprint Deployment (Recommended)

1. Push your repository to **GitHub** or **GitLab**.
2. Log into your [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** -> **Blueprints**.
4. Connect your GitHub repository.
5. Render will automatically detect `render.yaml` and prompt you for missing environment variables (`MONGO_URL`, `RESEND_API_KEY`).
6. Enter your **MongoDB Atlas Connection String** in `MONGO_URL`.
7. Click **Apply**. Render will automatically build and deploy both your Backend service and Frontend static site.

---

### Option B: Manual Web Service Deployment

#### Deploying Backend (FastAPI Web Service)
1. In Render Dashboard, click **New +** -> **Web Service**.
2. Connect your repo.
3. Settings:
   - **Name**: `face-engine-backend`
   - **Environment**: `Python 3`
   - **Region**: Choose nearest region
   - **Build Command**: `pip install --upgrade pip setuptools wheel && pip install "numpy<2.0.0" Cython && pip install -r backend/requirements.txt && python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'], allowed_modules=['detection', 'recognition'])"`
   - **Start Command**: `cd backend && uvicorn server:app --host 0.0.0.0 --port $PORT`
4. Add Environment Variables:
   - `MONGO_URL`: `mongodb+srv://<username>:<password>@cluster0.mongodb.net/?retryWrites=true&w=majority`
   - `DB_NAME`: `sentinel_fr`
   - `JWT_SECRET`: *(A long random secret string)*
   - `CORS_ORIGINS`: `https://<your-frontend-name>.onrender.com`
   - `FACE_MATCH_THRESHOLD`: `0.42`
   - `UPLOAD_ROOT`: `./uploads`

#### Deploying Frontend (Static Site)
1. Click **New +** -> **Static Site**.
2. Connect your repo.
3. Settings:
   - **Name**: `face-engine-frontend`
   - **Build Command**: `cd frontend && npm install && npm run build`
   - **Publish Directory**: `frontend/build`
4. Add Environment Variable:
   - `REACT_APP_BACKEND_URL`: `https://face-engine-backend.onrender.com` (Use your actual backend URL)
5. Click **Create Static Site**.

---

## 🔍 Verification Checklist

- [x] `.env` created in root, `backend/`, and `frontend/`
- [x] `.env.example` & `.example.env` templates created with all variables
- [x] Graceful fallback defaults added to backend (`server.py`) and frontend (`api.js`)
- [x] `render.yaml` generated for Render Blueprints
- [x] `.gitignore` updated to ignore `.env` while preserving `.env.example` and `.example.env`
