import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiError } from "@/lib/api";
import { ShieldCheck, LockKey, Envelope } from "@phosphor-icons/react";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      nav("/");
    } catch (err) {
      setError(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-white flex">
      <div className="hidden lg:flex flex-1 relative border-r border-white/10 overflow-hidden">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              "url(https://images.unsplash.com/photo-1528312635006-8ea0bc49ec63?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxOTB8MHwxfHNlYXJjaHwxfHxjY3R2JTIwY2FtZXJhJTIwbGVuc2VzfGVufDB8fHx8MTc4NTI5ODQyNXww&ixlib=rb-4.1.0&q=85)",
            backgroundSize: "cover",
            backgroundPosition: "center",
            filter: "grayscale(1) brightness(0.35)",
          }}
        />
        <div className="absolute inset-0" style={{ background: "linear-gradient(180deg, rgba(10,10,10,0.4), #0A0A0A 90%)" }} />
        <div className="relative z-10 p-14 flex flex-col justify-between w-full">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-md bg-[#00FF66]/10 border border-[#00FF66]/30 flex items-center justify-center">
              <ShieldCheck size={22} weight="duotone" color="#00FF66" />
            </div>
            <div>
              <div className="font-heading text-lg font-bold tracking-tight">SENTINEL / FR</div>
              <div className="font-mono text-[10px] tracking-[0.3em] text-white/40 uppercase">Facial Recognition Command Center</div>
            </div>
          </div>

          <div>
            <h1 className="font-heading text-5xl font-light tracking-tight leading-none max-w-lg">
              Precision identity at the edge<span className="text-[#00FF66]">.</span>
            </h1>
            <p className="mt-6 text-white/60 text-sm max-w-md font-mono leading-relaxed">
              Real-time face recognition powered by SCRFD detection and ArcFace embeddings.
              Multi-frame verification. Sub-second recall across 100,000+ enrolled identities.
            </p>
            <div className="mt-10 grid grid-cols-3 gap-6 max-w-md">
              {[
                ["99.4%", "ACCURACY"],
                ["<800ms", "LATENCY"],
                ["24/7", "MONITORING"],
              ].map(([v, l]) => (
                <div key={l}>
                  <div className="font-mono text-2xl text-[#00FF66]">{v}</div>
                  <div className="text-[10px] uppercase tracking-[0.25em] text-white/40 font-mono mt-1">{l}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="w-full lg:w-[520px] flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm" data-testid="login-form">
          <div className="mb-10">
            <div className="text-[10px] tracking-[0.3em] uppercase text-[#00FF66] font-mono mb-4">Restricted access</div>
            <h2 className="font-heading text-3xl tracking-tight">Operator sign-in</h2>
            <p className="text-white/50 text-sm mt-2 font-mono">Use your admin credentials to continue.</p>
          </div>

          <label className="block text-[10px] tracking-[0.25em] uppercase text-white/50 font-mono mb-2">Email</label>
          <div className="flex items-center gap-2 border border-white/10 bg-[#121212] rounded-md px-3 py-2.5 mb-5 focus-within:border-[#00FF66]/50">
            <Envelope size={16} className="text-white/40" />
            <input
              data-testid="login-email"
              type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              className="bg-transparent outline-none w-full text-sm font-mono"
              placeholder="you@company.com"
            />
          </div>

          <label className="block text-[10px] tracking-[0.25em] uppercase text-white/50 font-mono mb-2">Password</label>
          <div className="flex items-center gap-2 border border-white/10 bg-[#121212] rounded-md px-3 py-2.5 mb-6 focus-within:border-[#00FF66]/50">
            <LockKey size={16} className="text-white/40" />
            <input
              data-testid="login-password"
              type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
              className="bg-transparent outline-none w-full text-sm font-mono"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div data-testid="login-error" className="mb-4 text-xs text-[#FF3B30] font-mono border border-[#FF3B30]/30 bg-[#FF3B30]/5 rounded-md px-3 py-2">
              {error}
            </div>
          )}

          <button
            data-testid="login-submit"
            disabled={busy}
            className="w-full py-3 rounded-md bg-[#00FF66] text-black font-heading font-bold text-sm tracking-wide hover:bg-[#00E65C] transition-colors disabled:opacity-60"
          >
            {busy ? "Verifying..." : "Sign in →"}
          </button>

          <div className="mt-8 text-[10px] tracking-[0.25em] uppercase text-white/30 font-mono text-center">
            © Sentinel FR • v1.0
          </div>
        </form>
      </div>
    </div>
  );
}
