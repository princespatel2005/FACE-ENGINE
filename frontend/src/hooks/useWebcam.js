import { useEffect, useRef, useState } from "react";

/**
 * Reusable webcam capture hook. Returns:
 *   videoRef, canvasRef, running, error, start(), stop(), snap() -> dataURL
 */
export default function useWebcam() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const start = async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setRunning(true);
    } catch (e) {
      setError(e?.message || "Could not access camera");
    }
  };

  const stop = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setRunning(false);
  };

  useEffect(() => () => stop(), []);

  const snap = (quality = 0.85) => {
    const v = videoRef.current;
    const c = canvasRef.current;
    if (!v || !c) return null;
    const w = v.videoWidth || 640;
    const h = v.videoHeight || 480;
    c.width = w; c.height = h;
    const ctx = c.getContext("2d");
    ctx.drawImage(v, 0, 0, w, h);
    return c.toDataURL("image/jpeg", quality);
  };

  return { videoRef, canvasRef, running, error, start, stop, snap };
}
