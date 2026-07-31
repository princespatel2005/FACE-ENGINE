"""Face recognition engine using insightface (SCRFD detector + w600k_r50 embeddings).

Loads the buffalo_l model on demand in a background thread to avoid blocking startup.
If the model cannot be loaded (offline, missing weights), the engine reports not ready
so callers can surface a helpful error to the UI.
"""
from __future__ import annotations

import base64
import io
import logging
import threading
from typing import List, Optional

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class Detection:
    __slots__ = ("bbox", "kps", "det_score", "embedding", "pose")

    def __init__(self, bbox, kps, det_score, embedding, pose):
        self.bbox = bbox            # [x1, y1, x2, y2]
        self.kps = kps              # 5x2 landmarks
        self.det_score = det_score
        self.embedding = embedding  # np.ndarray shape (512,) L2 normalized
        self.pose = pose            # [pitch, yaw, roll] or None


class FaceEngine:
    def __init__(self, model_name: str = "buffalo_l"):
        self.model_name = model_name
        self._app = None
        self._lock = threading.Lock()
        self._ready = False
        self._loading = False
        self._error: Optional[str] = None

    def status(self) -> dict:
        return {
            "ready": self._ready,
            "loading": self._loading,
            "error": self._error,
            "model": self.model_name,
        }

    def start_background_load(self):
        if self._ready or self._loading:
            return
        self._loading = True
        t = threading.Thread(target=self._load, daemon=True)
        t.start()

    def _load(self):
        try:
            logger.info("Loading insightface model %s ...", self.model_name)
            from insightface.app import FaceAnalysis  # heavy import

            app = FaceAnalysis(
                name=self.model_name,
                providers=["CPUExecutionProvider"],
                allowed_modules=["detection", "recognition"],
            )
            app.prepare(ctx_id=0, det_size=(640, 640))
            with self._lock:
                self._app = app
                self._ready = True
                self._loading = False
            logger.info("Face engine ready.")
        except Exception as e:  # noqa
            logger.exception("Failed to load face engine")
            with self._lock:
                self._error = f"{type(e).__name__}: {e}"
                self._loading = False

    # ---------- helpers ----------
    @staticmethod
    def decode_base64_image(data_url_or_b64: str) -> np.ndarray:
        """Decode data URL or base64 string into a BGR numpy array."""
        b64 = data_url_or_b64.split(",", 1)[1] if data_url_or_b64.startswith("data:") else data_url_or_b64
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        arr = np.array(img)
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    @staticmethod
    def blurriness(img_bgr: np.ndarray) -> float:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    @staticmethod
    def brightness(img_bgr: np.ndarray) -> float:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        return float(gray.mean())

    def quality_check(self, img_bgr: np.ndarray, face_bbox) -> Optional[str]:
        """Return None if OK, else a human message describing why the face is rejected."""
        x1, y1, x2, y2 = [int(v) for v in face_bbox]
        w, h = max(1, x2 - x1), max(1, y2 - y1)
        H, W = img_bgr.shape[:2]
        if w < 60 or h < 60:
            return "Face too small — please move closer to the camera."
        if x1 < 2 or y1 < 2 or x2 > W - 2 or y2 > H - 2:
            return "Face is partially outside the frame."
        crop = img_bgr[max(0, y1):min(H, y2), max(0, x1):min(W, x2)]
        if crop.size == 0:
            return "Face crop is empty."
        if self.blurriness(crop) < 40:
            return "Image is too blurry — please hold still."
        b = self.brightness(crop)
        if b < 35:
            return "Scene is too dark — increase lighting."
        if b > 235:
            return "Scene is over-exposed."
        return None

    def analyze(self, img_bgr: np.ndarray) -> List[Detection]:
        if not self._ready:
            return []
        faces = self._app.get(img_bgr)
        out: List[Detection] = []
        for f in faces:
            emb = f.normed_embedding.astype(np.float32)
            out.append(
                Detection(
                    bbox=[float(x) for x in f.bbox.tolist()],
                    kps=f.kps.tolist() if getattr(f, "kps", None) is not None else None,
                    det_score=float(f.det_score),
                    embedding=emb,
                    pose=getattr(f, "pose", None).tolist() if getattr(f, "pose", None) is not None else None,
                )
            )
        return out


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8
    return float(np.dot(a, b) / denom)


# Singleton
engine = FaceEngine()
