"""RTSP / IP camera worker: pulls frames in a background loop, runs face recognition,
and stores the latest annotated JPEG plus in-memory status. Snapshots are served via
a REST endpoint so the frontend can poll them.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np

from face_engine import engine, cosine_similarity

logger = logging.getLogger(__name__)


class CameraWorker:
    def __init__(self, cam_id: str, name: str, url: str, snapshot_dir: Path):
        self.cam_id = cam_id
        self.name = name
        self.url = url
        self.snapshot_dir = snapshot_dir
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self.status = {
            "id": cam_id, "name": name, "url": url, "state": "starting",
            "last_frame_at": None, "last_detections": [], "fps": 0.0, "error": None,
        }

    def start(self, on_detections):
        self._stop.clear()
        self._task = asyncio.create_task(self._run(on_detections))
        self.status["state"] = "starting"

    async def stop(self):
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except Exception:
                pass
        self.status["state"] = "stopped"

    async def _run(self, on_detections):
        loop = asyncio.get_running_loop()
        cap = await loop.run_in_executor(None, cv2.VideoCapture, self.url)
        if not cap.isOpened():
            self.status["state"] = "error"
            self.status["error"] = "Cannot open stream"
            logger.warning("Camera %s: cannot open %s", self.cam_id, self.url)
            return
        self.status["state"] = "running"
        self.status["error"] = None
        last_t = datetime.now(timezone.utc)
        while not self._stop.is_set():
            ok, frame = await loop.run_in_executor(None, cap.read)
            if not ok or frame is None:
                self.status["error"] = "Read failed"
                await asyncio.sleep(1.5)
                continue

            # Downscale for speed
            h, w = frame.shape[:2]
            if w > 960:
                scale = 960 / w
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

            dets = []
            if engine.status().get("ready"):
                try:
                    dets = await asyncio.to_thread(engine.analyze, frame)
                except Exception as e:  # noqa
                    logger.warning("analyze failed: %s", e)
                    dets = []

            annotated, det_summary = draw_annotations(frame, dets)
            # Save latest JPEG
            path = self.snapshot_dir / f"{self.cam_id}.jpg"
            await loop.run_in_executor(None, lambda: cv2.imwrite(str(path), annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 75]))
            now = datetime.now(timezone.utc)
            dt = (now - last_t).total_seconds()
            if dt > 0:
                self.status["fps"] = round(1.0 / max(dt, 0.001), 2)
            self.status["last_frame_at"] = now.isoformat()
            last_t = now
            self.status["last_detections"] = det_summary

            # Notify callback for identification hits
            try:
                await on_detections(self.cam_id, self.name, det_summary, annotated)
            except Exception as e:  # noqa
                logger.warning("on_detections callback failed: %s", e)

            await asyncio.sleep(1.0)

        cap.release()
        self.status["state"] = "stopped"


def draw_annotations(frame: np.ndarray, detections) -> tuple:
    """Simple annotation: draw boxes; identity lookup happens outside (async db)."""
    out = frame.copy()
    summary = []
    for d in detections:
        x1, y1, x2, y2 = [int(v) for v in d.bbox]
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 102), 2)
        summary.append({
            "bbox": [float(x1), float(y1), float(x2), float(y2)],
            "det_score": d.det_score,
            "embedding": d.embedding.tolist() if d.embedding is not None else None,
        })
    return out, summary


class CameraManager:
    def __init__(self, snapshot_dir: Path):
        self.workers: Dict[str, CameraWorker] = {}
        self.snapshot_dir = snapshot_dir
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    async def add(self, cam: dict, on_detections):
        await self.stop(cam["id"])
        w = CameraWorker(cam["id"], cam["name"], cam["url"], self.snapshot_dir)
        self.workers[cam["id"]] = w
        w.start(on_detections)

    async def stop(self, cam_id: str):
        w = self.workers.pop(cam_id, None)
        if w:
            await w.stop()

    def status(self, cam_id: str) -> dict:
        w = self.workers.get(cam_id)
        return w.status if w else {"id": cam_id, "state": "stopped"}

    def snapshot_path(self, cam_id: str) -> Path:
        return self.snapshot_dir / f"{cam_id}.jpg"
