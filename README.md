# Smart AI Face Recognition System (FACE-ENGINE)

An enterprise-grade, real-time AI face recognition system with FastAPI backend (InsightFace SCRFD detector + ResNet50 embeddings), React frontend, MongoDB storage, and alert management.

---

## 🚀 Quick Start (Local Execution)

### 1. Environment Setup
Copy the environment template files to `.env`:
```bash
cp .env.example .env
```
*(You can also find all required and optional variables documented in `.env.example` and `.example.env`)*.

### 2. Run Backend
```bash
cd backend
pip install -r requirements.txt
python server.py
```
Backend will start on `http://localhost:8000`.

### 3. Run Frontend
```bash
cd frontend
npm install
npm start
```
Frontend will open on `http://localhost:3000`.

---

## 📦 Deploying to Render

This repository includes a `render.yaml` blueprint.

1. Push this project to GitHub.
2. Go to Render Dashboard -> **New +** -> **Blueprints**.
3. Connect your repository.
4. Set your `MONGO_URL` (MongoDB Atlas URI) when prompted.

For detailed instructions, see [DEPLOYMENT.md](DEPLOYMENT.md).
