import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import axios from "axios";
import useWebcam from "@/hooks/useWebcam";
import { API, UPLOADS_BASE } from "@/lib/api";
import { CheckCircle, Warning, ShieldCheck } from "@phosphor-icons/react";

const CAPTURE_INTERVAL_MS = 6500;
const FRAMES = 12;

export default function Kiosk() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const { videoRef, canvasRef, running, error, start, stop, snap } = useWebcam();
  const [state, setState] = useState({ status: "idle" });
  const [countdown, setCountdown] = useState(0);
  const busy = useRef(false);

  useEffect(() => { start(); return () => stop(); /* eslint-disable-next-line */ }, []);

  useEffect(() => {
    if (!running || !token) return;
    let cancelled = false;
    const tick = async () => {
      if (busy.current || cancelled) return;
      busy.current = true;
      try {
        const frames = [];
        for (let i = 0; i < FRAMES; i++) {
          const img = snap(0.7);
          if (img) frames.push(img);
          await new Promise((r) => setTimeout(r, 120));
        }
        const { data } = await axios.post(`${API}/kiosk/verify`, {
          token, images: frames, camera_id: "kiosk",
        });
        if (!cancelled) setState(data);
      } catch (e) {
        if (!cancelled) setState({ status: "error", message: e?.response?.data?.detail || "Verification failed." });
      } finally {
        busy.current = false;
      }
    };
    tick();
    const iv = setInterval(tick, CAPTURE_INTERVAL_MS);
    // countdown ui
    const cd = setInterval(() => setCountdown((c) => (c > 0 ? c - 1 : Math.ceil(CAPTURE_INTERVAL_MS / 1000))), 1000);
    return () => { cancelled = true; clearInterval(iv); clearInterval(cd); };
  }, [running, token, snap]);

  const status = state.status;
  const bg = status === "known" ? "#00FF66" : status === "unknown" ? "#FF3B30" : "#0A0A0A";
  const vip = state.watchlist_status === "vip";
  const blocked = state.watchlist_status === "blocked";

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-white overflow-hidden relative">
      <div className="absolute inset-0 grid grid-cols-1 lg:grid-cols-5">
        <div className="lg:col-span-3 relative bg-black">
          <video ref={videoRef} playsInline muted className="w-full h-full object-cover" />
          <canvas ref={canvasRef} className="hidden" />
          {!running && (
            <div className="absolute inset-0 flex items-center justify-center text-white/40 font-mono text-sm">
              {error ? `Camera error: ${error}` : "Starting camera…"}
            </div>
          )}
          {/* Scanline overlay */}
          <div className="pointer-events-none absolute inset-0 mix-blend-overlay opacity-20" style={{ background: "repeating-linear-gradient(0deg, rgba(255,255,255,0.06) 0, rgba(255,255,255,0.06) 1px, transparent 1px, transparent 3px)" }} />
          <div className="absolute top-6 left-6 flex items-center gap-3">
            <div className="w-10 h-10 rounded-md bg-[#00FF66]/10 border border-[#00FF66]/30 flex items-center justify-center">
              <ShieldCheck size={22} weight="duotone" color="#00FF66" />
            </div>
            <div>
              <div className="font-heading text-lg tracking-tight">Sentinel FR · Kiosk</div>
              <div className="font-mono text-[10px] tracking-[0.3em] text-white/40 uppercase">Look at the camera</div>
            </div>
          </div>
          <div className="absolute bottom-6 left-6 font-mono text-[11px] tracking-[0.25em] uppercase text-white/40">
            Next scan in {countdown || "…"}s
          </div>
        </div>

        <div className="lg:col-span-2 p-10 flex flex-col justify-center" style={{ background: "#0A0A0A" }}>
          {!token && (
            <div className="border border-[#FFFF00]/40 bg-[#FFFF00]/5 rounded-md p-6">
              <div className="text-xs text-[#FFFF00] font-mono uppercase tracking-widest">Kiosk token missing</div>
              <p className="text-sm text-white/60 mt-2 font-mono">Open this page with <span className="text-white">?token=&lt;kiosk_token&gt;</span> — generate one in Settings.</p>
            </div>
          )}
          {token && status === "idle" && (
            <div className="text-white/40 font-mono text-sm">Warming up…</div>
          )}
          {token && status === "known" && (
            <div data-testid="kiosk-result-known" className={`rounded-md p-8 border-2`} style={{ borderColor: blocked ? "#FF3B30" : vip ? "#FFD400" : "#00FF66", background: blocked ? "rgba(255,59,48,0.05)" : vip ? "rgba(255,212,0,0.05)" : "rgba(0,255,102,0.05)" }}>
              <div className="flex items-center gap-2 mb-4">
                {blocked ? <Warning size={24} color="#FF3B30" weight="duotone" /> : <CheckCircle size={24} color={vip ? "#FFD400" : "#00FF66"} weight="duotone" />}
                <div className="text-xs font-mono uppercase tracking-[0.25em]" style={{ color: blocked ? "#FF3B30" : vip ? "#FFD400" : "#00FF66" }}>
                  {blocked ? "Access denied" : vip ? "VIP welcome" : "Welcome"}
                </div>
              </div>
              <div className="flex items-center gap-4">
                {state.thumbnail_url && <img src={UPLOADS_BASE + state.thumbnail_url} className="w-20 h-20 rounded-md object-cover border border-white/10" alt="" />}
                <div>
                  <div className="font-heading text-4xl">{state.name}</div>
                  <div className="text-sm text-white/50 font-mono mt-1">{state.employee_id || "—"} · {state.department || "—"}</div>
                </div>
              </div>
              <div className="mt-6 grid grid-cols-2 gap-4 font-mono text-sm">
                <div>
                  <div className="text-white/40 uppercase tracking-widest text-[10px]">Confidence</div>
                  <div className="text-2xl mt-1" style={{ color: blocked ? "#FF3B30" : vip ? "#FFD400" : "#00FF66" }}>{(state.similarity * 100).toFixed(1)}%</div>
                </div>
                <div>
                  <div className="text-white/40 uppercase tracking-widest text-[10px]">Attendance</div>
                  <div className="text-2xl mt-1 text-white">{state.attendance_logged ? "Logged" : "Already logged"}</div>
                </div>
              </div>
            </div>
          )}
          {token && status === "unknown" && (
            <div data-testid="kiosk-result-unknown" className="rounded-md p-8 border-2 border-[#FF3B30] bg-[#FF3B30]/5">
              <div className="flex items-center gap-2 mb-3"><Warning size={24} color="#FF3B30" weight="duotone" /><div className="text-xs text-[#FF3B30] font-mono uppercase tracking-[0.25em]">Not recognised</div></div>
              <div className="font-heading text-3xl">Please contact reception</div>
              <div className="text-sm text-white/50 mt-3 font-mono">Your face was captured for review.</div>
            </div>
          )}
          {token && (status === "no_face" || status === "error") && (
            <div className="rounded-md p-8 border border-white/10">
              <div className="text-xs text-white/60 font-mono uppercase tracking-[0.25em]">{status === "no_face" ? "Look directly at the camera" : "Scan error"}</div>
              <div className="mt-2 text-sm text-white/70">{state.message || "Adjusting…"}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
