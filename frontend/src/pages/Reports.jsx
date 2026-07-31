import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiError, UPLOADS_BASE } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import { Star, TrendUp, PaperPlaneTilt } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Reports() {
  const [ov, setOv] = useState(null);
  const [spenders, setSpenders] = useState([]);
  const [freq, setFreq] = useState([]);
  const [vips, setVips] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [a, b, c, d] = await Promise.all([
        api.get("/reports/overview?days=7"),
        api.get("/reports/top-spenders?limit=10"),
        api.get("/reports/frequent-visitors?days=30&limit=10"),
        api.get("/reports/vips"),
      ]);
      setOv(a.data); setSpenders(b.data); setFreq(c.data); setVips(d.data);
    } catch (e) { toast.error(apiError(e)); }
  };
  useEffect(() => { load(); }, []);

  const sendDigest = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/reports/send-digest");
      toast.success(`Digest sent to ${data.recipient}`);
    } catch (e) { toast.error(apiError(e)); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="Weekly footfall, VIP activity, and top-spending customers"
        right={
          <button data-testid="send-digest-btn" onClick={sendDigest} disabled={busy} className="px-4 py-2 rounded-md bg-[#00FF66] text-black font-mono text-xs uppercase tracking-widest hover:bg-[#00E65C] disabled:opacity-40 flex items-center gap-2">
            <PaperPlaneTilt size={12} /> {busy ? "Sending…" : "Send digest now"}
          </button>
        }
      />

      <div className="px-8 py-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            ["Visits (7d)", ov?.total_visits ?? "—", "#fff"],
            ["Unique customers", ov?.unique_visitors ?? "—", "#00FF66"],
            ["VIP visits", ov?.vip_visits ?? "—", "#FFD400"],
            ["Unknowns (7d)", ov?.unknown ?? "—", "#FF3B30"],
          ].map(([l, v, c]) => (
            <div key={l} className="bg-[#121212] border border-white/10 rounded-md p-5">
              <div className="text-[10px] tracking-[0.25em] uppercase text-white/40 font-mono">{l}</div>
              <div className="mt-3 font-mono text-3xl" style={{ color: c }}>{v}</div>
            </div>
          ))}
        </div>

        <div className="bg-[#121212] border border-white/10 rounded-md p-5">
          <div className="flex items-center justify-between mb-6">
            <div>
              <div className="text-[10px] tracking-[0.25em] uppercase text-white/40 font-mono">Peak hours</div>
              <div className="font-heading text-xl mt-1">Visits by hour of day (7d)</div>
            </div>
            <TrendUp size={20} weight="duotone" color="#00FF66" />
          </div>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <BarChart data={(ov?.peak_hours || []).map((p) => ({ hour: `${p.hour}:00`, count: p.count }))}>
                <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="hour" stroke="#71717A" tick={{ fontFamily: "JetBrains Mono", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis stroke="#71717A" tick={{ fontFamily: "JetBrains Mono", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "#0A0A0A", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6, fontFamily: "JetBrains Mono", fontSize: 12 }} cursor={{ fill: "rgba(0,255,102,0.05)" }} />
                <Bar dataKey="count" fill="#00FF66" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-[#121212] border border-white/10 rounded-md">
            <div className="px-5 py-4 border-b border-white/10">
              <div className="text-[10px] tracking-[0.25em] uppercase text-white/40 font-mono">Top spenders</div>
              <div className="font-heading text-lg mt-1">Lifetime revenue leaders</div>
            </div>
            <div className="divide-y divide-white/5">
              {spenders.length === 0 && <div className="px-5 py-8 text-white/40 font-mono text-sm text-center">No purchases logged yet.</div>}
              {spenders.map((u, i) => (
                <Link key={u.id} to={`/customers/${u.id}`} className="px-5 py-3 flex items-center gap-4 hover:bg-[#1A1A1A] transition-colors">
                  <div className="w-6 text-center font-mono text-xs text-white/40">{i + 1}</div>
                  <div className="w-9 h-9 rounded bg-white/5 border border-white/10 overflow-hidden">{u.thumbnail_url && <img src={UPLOADS_BASE + u.thumbnail_url} className="w-full h-full object-cover" alt="" />}</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm">{u.name}</div>
                    <div className="text-[11px] font-mono text-white/40">{u.total_visits} visits</div>
                  </div>
                  <div className="font-mono text-[#00FF66]">₹{Math.round(u.lifetime_spend).toLocaleString()}</div>
                </Link>
              ))}
            </div>
          </div>

          <div className="bg-[#121212] border border-white/10 rounded-md">
            <div className="px-5 py-4 border-b border-white/10">
              <div className="text-[10px] tracking-[0.25em] uppercase text-white/40 font-mono">Frequent visitors</div>
              <div className="font-heading text-lg mt-1">Most active in last 30 days</div>
            </div>
            <div className="divide-y divide-white/5">
              {freq.length === 0 && <div className="px-5 py-8 text-white/40 font-mono text-sm text-center">No repeat visits yet.</div>}
              {freq.map((u, i) => (
                <Link key={u.id} to={`/customers/${u.id}`} className="px-5 py-3 flex items-center gap-4 hover:bg-[#1A1A1A] transition-colors">
                  <div className="w-6 text-center font-mono text-xs text-white/40">{i + 1}</div>
                  <div className="w-9 h-9 rounded bg-white/5 border border-white/10 overflow-hidden">{u.thumbnail_url && <img src={UPLOADS_BASE + u.thumbnail_url} className="w-full h-full object-cover" alt="" />}</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm">{u.name}</div>
                    <div className="text-[11px] font-mono text-white/40">Last: {u.most_recent_at ? new Date(u.most_recent_at).toLocaleDateString() : "—"}</div>
                  </div>
                  <div className="font-mono text-white">{u.recent_visits}</div>
                </Link>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-[#121212] border border-white/10 rounded-md">
          <div className="px-5 py-4 border-b border-white/10 flex items-center gap-2">
            <Star size={16} weight="fill" color="#FFD400" />
            <div className="font-heading text-lg">VIP customers</div>
            <div className="text-[11px] font-mono text-white/40">({vips.length})</div>
          </div>
          {vips.length === 0 ? (
            <div className="px-5 py-8 text-white/40 font-mono text-sm text-center">Flag customers as VIP from the Customers table to see them here.</div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 p-4">
              {vips.map((u) => (
                <Link key={u.id} to={`/customers/${u.id}`} className="border border-[#FFD400]/30 bg-[#FFD400]/5 rounded-md p-3 hover:bg-[#FFD400]/10 transition-colors">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded bg-white/5 border border-white/10 overflow-hidden">{u.thumbnail_url && <img src={UPLOADS_BASE + u.thumbnail_url} className="w-full h-full object-cover" alt="" />}</div>
                    <div className="min-w-0">
                      <div className="text-sm truncate">{u.name}</div>
                      <div className="text-[11px] font-mono text-[#FFD400]">₹{Math.round(u.lifetime_spend).toLocaleString()}</div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
