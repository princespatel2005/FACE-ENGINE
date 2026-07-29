import { useEffect, useRef, useState } from "react";
import { api, apiError } from "@/lib/api";
import useWebcam from "@/hooks/useWebcam";
import PageHeader from "@/components/PageHeader";
import { Camera, Play, Stop, Aperture } from "@phosphor-icons/react";
import { toast } from "sonner";

const FRAMES = 15;

export default function LiveRecognition() {
  const { videoRef, canvasRef, running, error, start, stop, snap } = useWebcam();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [detections, setDetections] = useState([]);
  const [progress, setProgress] = useState(0);
  const overlayRef = useRef(null);

  // Continuous single-frame detection loop for on-screen bounding boxes
  useEffect(() => {
    if (!running) return;
    let cancelled = false;
    const loop = async () => {
      while (!cancelled) {
        const img = snap(0.6);
        if (img) {
          try {
            const { data } = await api.post("/recognize", { image: img, camera_id: "webcam-01" });
            if (!cancelled) setDetections(data.detections || []);
          } catch (_) {
            // ignore transient errors while looping
          }
        }
        await new Promise((r) => setTimeout(r, 900));
      }
    };
    loop();
    return () => { cancelled = true; };
  }, [running, snap]);

  const verify = async () => {
    if (!running || busy) return;
    setBusy(true);
    setResult(null);
    setProgress(0);
    const frames = [];
    for (let i = 0; i < FRAMES; i++) {
      const f = snap(0.75);
      if (f) frames.push(f);
      setProgress(Math.round(((i + 1) / FRAMES) * 100));
      await new Promise((r) => setTimeout(r, 120));
    }
    try {
      const { data } = await api.post("/recognize/multi", { images: frames, camera_id: "webcam-01" });
      setResult(data);
      if (data.status === "known") {
        toast.success(`Identified: ${data.name}`, { description: `Confidence ${(data.similarity * 100).toFixed(1)}%` });
      } else if (data.status === "unknown") {
        toast.error("Unknown person", { description: "Face saved for review." });
      } else {
        toast("No usable face detected in the frames.");
      }
    } catch (e) {
      toast.error(apiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Live Recognition"
        subtitle="Real-time SCRFD detection with multi-frame ArcFace verification"
        right={
          <div className="flex items-center gap-2">
            {!running ? (
              <button data-testid="start-camera-btn" onClick={start} className="px-4 py-2 rounded-md bg-[#00FF66] text-black font-mono text-xs tracking-widest uppercase hover:bg-[#00E65C] transition-colors flex items-center gap-2">
                <Play size={14} weight="fill" /> Start camera
              </button>
            ) : (
              <button data-testid="stop-camera-btn" onClick={stop} className="px-4 py-2 rounded-md border border-white/20 text-white font-mono text-xs tracking-widest uppercase hover:bg-white/5 transition-colors flex items-center gap-2">
                <Stop size={14} weight="fill" /> Stop
              </button>
            )}
            <button
              data-testid="verify-btn"
              disabled={!running || busy}
              onClick={verify}
              className="px-4 py-2 rounded-md bg-white text-black font-mono text-xs tracking-widest uppercase hover:bg-white/80 transition-colors flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Aperture size={14} weight="duotone" />
              {busy ? `Capturing ${progress}%` : `Verify (${FRAMES} frames)`}
            </button>
          </div>
        }
      />

      <div className="px-8 py-8 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 relative bg-black border border-white/10 rounded-md overflow-hidden aspect-video" ref={overlayRef}>
          {!running && (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-white/40 font-mono text-sm gap-3">
              <Camera size={48} weight="thin" />
              <div>Camera offline. Press <span className="text-white">START CAMERA</span>.</div>
              {error && <div className="text-[#FF3B30] text-xs">{error}</div>}
            </div>
          )}
          <video data-testid="live-video" ref={videoRef} playsInline muted className="w-full h-full object-cover" />
          <canvas ref={canvasRef} className="hidden" />

          {running && detections.map((d, i) => {
            if (!d.bbox) return null;
            const v = videoRef.current;
            if (!v || !v.videoWidth) return null;
            const scaleX = 100 / v.videoWidth;
            const scaleY = 100 / v.videoHeight;
            const [x1, y1, x2, y2] = d.bbox;
            const isBlocked = d.watchlist_status === "blocked";
            const isVip = d.watchlist_status === "vip";
            const color = isBlocked ? "#FF3B30"
              : isVip ? "#FFD400"
              : d.status === "known" ? "#00FF66"
              : d.status === "unknown" ? "#FF3B30" : "#FFFF00";
            const label = isBlocked ? `⚠ BLOCKED · ${d.name}`
              : isVip ? `★ VIP · ${d.name}`
              : d.status === "known" ? `${d.name} • ${(d.similarity * 100).toFixed(0)}%`
              : d.status === "unknown" ? "UNKNOWN"
              : (d.message || "LOW QUALITY");
            return (
              <div key={i}
                style={{
                  position: "absolute",
                  left: `${x1 * scaleX}%`, top: `${y1 * scaleY}%`,
                  width: `${(x2 - x1) * scaleX}%`, height: `${(y2 - y1) * scaleY}%`,
                  border: `2px solid ${color}`,
                  boxShadow: `0 0 24px ${color}66`,
                }}
              >
                <div className="absolute -top-6 left-0 px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest whitespace-nowrap" style={{ background: color, color: "#000" }}>
                  {label}
                </div>
              </div>
            );
          })}

          {running && (
            <div className="absolute top-3 left-3 flex items-center gap-2 bg-black/60 backdrop-blur-sm px-2.5 py-1 rounded font-mono text-[10px] uppercase tracking-[0.25em]">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#00FF66] animate-pulse" /> Live
            </div>
          )}
        </div>

        <div className="bg-[#121212] border border-white/10 rounded-md p-5">
          <div className="text-[10px] tracking-[0.25em] uppercase text-white/40 font-mono">Verification result</div>

          {!result && (
            <div className="mt-6 text-sm text-white/50 font-mono leading-relaxed">
              Press <span className="text-white">VERIFY</span> to capture {FRAMES} frames and run majority-vote identification.
            </div>
          )}

          {result?.status === "known" && (
            <div data-testid="result-known" className="mt-6">
              <div className={`border rounded-md p-4 ${
                result.watchlist_status === "blocked" ? "border-[#FF3B30]/60 bg-[#FF3B30]/10" :
                result.watchlist_status === "vip" ? "border-[#FFD400]/60 bg-[#FFD400]/10" :
                "border-[#00FF66]/40 bg-[#00FF66]/5"
              }`}>
                <div className={`text-xs font-mono tracking-widest uppercase ${
                  result.watchlist_status === "blocked" ? "text-[#FF3B30]" :
                  result.watchlist_status === "vip" ? "text-[#FFD400]" :
                  "text-[#00FF66]"
                }`}>
                  {result.watchlist_status === "blocked" ? "⚠ BLOCKED IDENTITY" :
                   result.watchlist_status === "vip" ? "★ VIP IDENTITY" :
                   "Identity confirmed"}
                </div>
                <div className="font-heading text-2xl mt-2">{result.name}</div>
                <div className="text-xs text-white/50 font-mono mt-1">{result.employee_id || "—"} · {result.department || "—"}</div>
                <div className="mt-4 grid grid-cols-2 gap-4 text-xs font-mono">
                  <div><div className="text-white/40 uppercase tracking-widest">Similarity</div><div className="text-[#00FF66] text-lg">{(result.similarity * 100).toFixed(1)}%</div></div>
                  <div><div className="text-white/40 uppercase tracking-widest">Votes</div><div className="text-white text-lg">{result.votes}/{result.frames}</div></div>
                </div>
                {result.attendance_logged && (
                  <div className="mt-4 text-[10px] uppercase tracking-widest font-mono text-[#00FF66]">
                    ✓ Attendance recorded
                  </div>
                )}
              </div>
            </div>
          )}

          {result?.status === "unknown" && (
            <div data-testid="result-unknown" className="mt-6 border border-[#FF3B30]/40 bg-[#FF3B30]/5 rounded-md p-4">
              <div className="text-xs text-[#FF3B30] font-mono tracking-widest uppercase">Unknown person</div>
              <div className="font-heading text-xl mt-2">No match found</div>
              <div className="text-xs text-white/50 font-mono mt-2">Face image saved for review under Unknown Faces.</div>
            </div>
          )}

          {result?.status === "no_face" && (
            <div className="mt-6 border border-white/10 rounded-md p-4">
              <div className="text-xs text-white/60 font-mono uppercase tracking-widest">No usable face</div>
              <div className="text-sm text-white/60 mt-2">{result.message}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
