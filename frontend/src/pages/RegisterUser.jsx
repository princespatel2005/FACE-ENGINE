import { useState } from "react";
import { api, apiError } from "@/lib/api";
import useWebcam from "@/hooks/useWebcam";
import PageHeader from "@/components/PageHeader";
import { Play, Stop, CheckCircle, UserPlus } from "@phosphor-icons/react";
import { toast } from "sonner";

const POSES = [
  "Look straight at the camera",
  "Turn head slightly LEFT",
  "Turn head slightly RIGHT",
  "Tilt head UP",
  "Tilt head DOWN",
  "SMILE naturally",
  "Neutral expression",
];
const IMAGES_PER_POSE = 7;
const TOTAL = POSES.length * IMAGES_PER_POSE; // 49 ≈ 50

export default function RegisterUser() {
  const { videoRef, canvasRef, running, error, start, stop, snap } = useWebcam();
  const [step, setStep] = useState(0); // 0 form, 1 capture, 2 done
  const [form, setForm] = useState({ name: "", employee_id: "", department: "", phone: "", email: "" });
  const [userId, setUserId] = useState(null);
  const [poseIdx, setPoseIdx] = useState(0);
  const [captured, setCaptured] = useState(0);
  const [enrolling, setEnrolling] = useState(false);
  const [summary, setSummary] = useState(null);
  const [frames, setFrames] = useState([]);

  const createUser = async (e) => {
    e.preventDefault();
    try {
      const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v));
      const { data } = await api.post("/users", payload);
      setUserId(data.id);
      setStep(1);
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  const captureFrame = () => {
    if (!running) return;
    const img = snap(0.85);
    if (!img) return;
    const nextFrames = [...frames, img];
    setFrames(nextFrames);
    const nextCount = captured + 1;
    setCaptured(nextCount);
    const inPose = nextCount % IMAGES_PER_POSE;
    if (inPose === 0 && poseIdx < POSES.length - 1) {
      setPoseIdx(poseIdx + 1);
      toast(`Pose ${poseIdx + 2}/${POSES.length}: ${POSES[poseIdx + 1]}`);
    }
  };

  const finish = async () => {
    setEnrolling(true);
    try {
      const { data } = await api.post(`/users/${userId}/enroll`, { images: frames });
      setSummary(data);
      setStep(2);
      stop();
      toast.success(`Enrollment complete — ${data.saved} embeddings saved`);
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setEnrolling(false);
    }
  };

  const percent = Math.round((captured / TOTAL) * 100);

  return (
    <div>
      <PageHeader title="Register User" subtitle="Multi-pose enrollment with quality-gated embedding capture" />

      <div className="px-8 py-8 max-w-5xl">
        {step === 0 && (
          <form onSubmit={createUser} className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-[#121212] border border-white/10 rounded-md p-6" data-testid="register-form">
            <div className="md:col-span-2 flex items-center gap-3 pb-3 border-b border-white/10">
              <UserPlus size={20} weight="duotone" color="#00FF66" />
              <div className="font-heading text-lg">Identity details</div>
            </div>
            {[
              ["name", "Full name", true],
              ["employee_id", "Employee ID", false],
              ["department", "Department", false],
              ["phone", "Phone", false],
              ["email", "Email", false],
            ].map(([k, label, required]) => (
              <label key={k} className="block">
                <div className="text-[10px] tracking-[0.25em] uppercase text-white/50 font-mono mb-2">{label}{required && " *"}</div>
                <input
                  data-testid={`register-input-${k}`}
                  required={required}
                  value={form[k]}
                  onChange={(e) => setForm({ ...form, [k]: e.target.value })}
                  className="w-full bg-[#0A0A0A] border border-white/10 rounded-md px-3 py-2.5 text-sm font-mono outline-none focus:border-[#00FF66]/50"
                />
              </label>
            ))}
            <div className="md:col-span-2 flex justify-end pt-2">
              <button data-testid="register-continue-btn" className="px-6 py-2.5 rounded-md bg-[#00FF66] text-black font-mono text-xs tracking-widest uppercase hover:bg-[#00E65C] transition-colors">
                Continue to capture →
              </button>
            </div>
          </form>
        )}

        {step === 1 && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 relative bg-black border border-white/10 rounded-md overflow-hidden aspect-video">
              {!running && (
                <div className="absolute inset-0 flex items-center justify-center text-white/40 font-mono text-sm">Press START to enable camera.</div>
              )}
              <video ref={videoRef} playsInline muted className="w-full h-full object-cover" />
              <canvas ref={canvasRef} className="hidden" />
              {running && (
                <>
                  <div className="absolute top-3 left-3 bg-black/60 backdrop-blur-sm px-3 py-1 rounded font-mono text-[10px] uppercase tracking-[0.25em]">
                    Pose {poseIdx + 1}/{POSES.length}
                  </div>
                  <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-4">
                    <div className="font-mono text-lg text-[#00FF66]">{POSES[poseIdx]}</div>
                    <div className="font-mono text-xs text-white/50 mt-1">Take {IMAGES_PER_POSE} shots per pose · {captured}/{TOTAL} total</div>
                  </div>
                </>
              )}
              {error && <div className="absolute inset-0 flex items-center justify-center text-[#FF3B30] font-mono text-xs">{error}</div>}
            </div>

            <div className="bg-[#121212] border border-white/10 rounded-md p-5 flex flex-col">
              <div className="text-[10px] tracking-[0.25em] uppercase text-white/40 font-mono">Capture progress</div>
              <div className="mt-4 font-mono text-4xl text-[#00FF66]">{captured}<span className="text-white/30 text-2xl">/{TOTAL}</span></div>
              <div className="mt-3 h-1.5 rounded-full bg-white/5 overflow-hidden">
                <div className="h-full bg-[#00FF66]" style={{ width: `${percent}%`, transition: "width 200ms" }} />
              </div>

              <div className="mt-6 grid grid-cols-2 gap-2">
                {!running ? (
                  <button onClick={start} data-testid="capture-start-btn" className="col-span-2 py-2.5 rounded-md bg-[#00FF66] text-black font-mono text-xs uppercase tracking-widest flex items-center justify-center gap-2 hover:bg-[#00E65C] transition-colors">
                    <Play size={14} weight="fill" /> Start camera
                  </button>
                ) : (
                  <>
                    <button data-testid="capture-frame-btn" onClick={captureFrame} disabled={captured >= TOTAL} className="col-span-2 py-2.5 rounded-md bg-white text-black font-mono text-xs uppercase tracking-widest hover:bg-white/80 transition-colors disabled:opacity-40">
                      Capture frame ({(captured % IMAGES_PER_POSE) + 1}/{IMAGES_PER_POSE})
                    </button>
                    <button onClick={stop} className="col-span-2 py-2 rounded-md border border-white/10 font-mono text-[10px] uppercase tracking-widest text-white/60 hover:text-white hover:bg-white/5 flex items-center justify-center gap-1">
                      <Stop size={12} /> Stop
                    </button>
                  </>
                )}
                <button
                  data-testid="finish-enroll-btn"
                  onClick={finish}
                  disabled={captured < 5 || enrolling}
                  className="col-span-2 mt-2 py-2.5 rounded-md border border-[#00FF66]/40 text-[#00FF66] font-mono text-xs uppercase tracking-widest hover:bg-[#00FF66]/10 disabled:opacity-40"
                >
                  {enrolling ? "Enrolling..." : "Finish & enroll"}
                </button>
              </div>

              <div className="mt-6 text-[11px] text-white/40 font-mono leading-relaxed">
                Follow the on-screen pose cue. Blurry, dark, or partial faces are automatically rejected during enrollment.
              </div>
            </div>
          </div>
        )}

        {step === 2 && summary && (
          <div className="bg-[#121212] border border-[#00FF66]/30 rounded-md p-8 text-center" data-testid="enroll-summary">
            <CheckCircle size={40} weight="duotone" color="#00FF66" className="mx-auto" />
            <div className="mt-4 font-heading text-2xl">Enrollment complete</div>
            <div className="mt-2 text-sm text-white/60 font-mono">
              {summary.saved} embeddings saved · {summary.rejected?.length || 0} frames rejected
            </div>
            <div className="mt-6 flex gap-3 justify-center">
              <button onClick={() => { setStep(0); setForm({ name: "", employee_id: "", department: "", phone: "", email: "" }); setUserId(null); setPoseIdx(0); setCaptured(0); setFrames([]); setSummary(null); }} className="px-5 py-2 rounded-md border border-white/20 font-mono text-xs uppercase tracking-widest hover:bg-white/5">
                Enroll another
              </button>
              <a href="/users" className="px-5 py-2 rounded-md bg-[#00FF66] text-black font-mono text-xs uppercase tracking-widest hover:bg-[#00E65C]">
                View users →
              </a>
            </div>
            {summary.rejected?.length > 0 && (
              <div className="mt-8 text-left text-xs text-white/50 font-mono border-t border-white/10 pt-4">
                <div className="uppercase tracking-widest mb-2">Rejected frames</div>
                {summary.rejected.slice(0, 5).map((r, i) => (
                  <div key={i}>• Frame {r.index}: {r.reason}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
