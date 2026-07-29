import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { toast } from "sonner";
import { PaperPlaneTilt, Key, Bell, Copy } from "@phosphor-icons/react";

export default function Settings() {
  const [s, setS] = useState({ alert_email: "", kiosk_token: "" });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => { (async () => {
    try { const { data } = await api.get("/settings"); setS(data); } finally { setLoading(false); }
  })(); }, []);

  const save = async () => {
    setBusy(true);
    try { await api.patch("/settings", s); toast.success("Settings saved"); }
    catch (e) { toast.error(apiError(e)); }
    finally { setBusy(false); }
  };

  const testEmail = async () => {
    try { const { data } = await api.post("/settings/test-email"); toast.success(`Sent to ${data.recipient}`); }
    catch (e) { toast.error(apiError(e)); }
  };

  const generateToken = () => {
    const t = Array.from(crypto.getRandomValues(new Uint8Array(24))).map((b) => b.toString(16).padStart(2, "0")).join("");
    setS({ ...s, kiosk_token: t });
  };

  const copy = (text) => { navigator.clipboard.writeText(text); toast("Copied to clipboard"); };

  const kioskUrl = typeof window !== "undefined" ? `${window.location.origin}/kiosk?token=${encodeURIComponent(s.kiosk_token || "")}` : "";

  if (loading) return <div className="p-10 font-mono text-sm text-white/40">Loading…</div>;

  return (
    <div>
      <PageHeader title="Settings" subtitle="Alert delivery and public kiosk configuration" />
      <div className="px-8 py-8 max-w-3xl space-y-6">
        <section className="bg-[#121212] border border-white/10 rounded-md p-6">
          <div className="flex items-center gap-2 pb-4 border-b border-white/10">
            <Bell size={18} weight="duotone" color="#00FF66" />
            <div className="font-heading text-lg">Unknown-face alerts</div>
          </div>
          <label className="block mt-5">
            <div className="text-[10px] tracking-[0.25em] uppercase text-white/50 font-mono mb-2">Recipient email</div>
            <input data-testid="alert-email-input" type="email" value={s.alert_email || ""} onChange={(e) => setS({ ...s, alert_email: e.target.value })} placeholder="alerts@yourcompany.com" className="w-full bg-[#0A0A0A] border border-white/10 rounded-md px-3 py-2.5 text-sm font-mono outline-none focus:border-[#00FF66]/50" />
            <div className="mt-2 text-[11px] text-white/40 font-mono">
              Using Resend sandbox sender <span className="text-white/70">onboarding@resend.dev</span> — emails are only delivered to the address you signed up with. Verify a domain in Resend to send anywhere.
            </div>
          </label>
          <div className="mt-5 flex gap-2">
            <button data-testid="save-settings-btn" onClick={save} disabled={busy} className="px-5 py-2 rounded-md bg-[#00FF66] text-black font-mono text-xs uppercase tracking-widest hover:bg-[#00E65C] disabled:opacity-40">
              {busy ? "Saving…" : "Save"}
            </button>
            <button data-testid="test-email-btn" onClick={testEmail} className="px-5 py-2 rounded-md border border-white/10 text-white/70 font-mono text-xs uppercase tracking-widest hover:bg-white/5 flex items-center gap-1.5">
              <PaperPlaneTilt size={12} /> Send test
            </button>
          </div>
        </section>

        <section className="bg-[#121212] border border-white/10 rounded-md p-6">
          <div className="flex items-center gap-2 pb-4 border-b border-white/10">
            <Key size={18} weight="duotone" color="#FFFF00" />
            <div className="font-heading text-lg">Kiosk access</div>
          </div>
          <div className="mt-5">
            <div className="text-[10px] tracking-[0.25em] uppercase text-white/50 font-mono mb-2">Kiosk token</div>
            <div className="flex gap-2">
              <input data-testid="kiosk-token-input" value={s.kiosk_token || ""} onChange={(e) => setS({ ...s, kiosk_token: e.target.value })} placeholder="Generate a random token" className="flex-1 bg-[#0A0A0A] border border-white/10 rounded-md px-3 py-2.5 text-sm font-mono outline-none focus:border-[#00FF66]/50" />
              <button data-testid="generate-token-btn" onClick={generateToken} className="px-4 py-2 rounded-md border border-white/10 font-mono text-xs uppercase tracking-widest text-white/70 hover:bg-white/5">Generate</button>
            </div>
            {s.kiosk_token && (
              <div className="mt-4 p-3 rounded-md bg-[#0A0A0A] border border-white/10 flex items-center gap-2">
                <div className="flex-1 font-mono text-xs text-[#00FF66] truncate">{kioskUrl}</div>
                <button onClick={() => copy(kioskUrl)} className="p-1.5 rounded text-white/50 hover:text-white hover:bg-white/5"><Copy size={14} /></button>
              </div>
            )}
            <div className="mt-3 text-[11px] text-white/40 font-mono">
              Open this URL on a tablet at a reception desk — visitors can look at the camera and get identified without logging in.
            </div>
          </div>
          <div className="mt-5">
            <button onClick={save} disabled={busy} className="px-5 py-2 rounded-md bg-[#00FF66] text-black font-mono text-xs uppercase tracking-widest hover:bg-[#00E65C] disabled:opacity-40">Save kiosk token</button>
          </div>
        </section>
      </div>
    </div>
  );
}
