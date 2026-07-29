import { useEffect, useState } from "react";
import { api, UPLOADS_BASE } from "@/lib/api";
import { Users, UserCheck, Warning, Cpu, TrendUp, ChartBar, Broadcast, Bell } from "@phosphor-icons/react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import PageHeader from "@/components/PageHeader";

const StatCard = ({ icon: Icon, label, value, accent = "#FFFFFF", sub, testid }) => (
  <div
    data-testid={testid}
    className="bg-[#121212] border border-white/10 rounded-md p-5 hover:border-white/20 transition-colors"
  >
    <div className="flex items-center justify-between mb-4">
      <div className="text-[10px] tracking-[0.25em] uppercase text-white/40 font-mono">{label}</div>
      <Icon size={18} weight="duotone" color={accent} />
    </div>
    <div className="font-mono text-3xl" style={{ color: accent }}>{value}</div>
    {sub && <div className="text-[11px] text-white/40 font-mono mt-2">{sub}</div>}
  </div>
);

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [s, r] = await Promise.all([
          api.get("/dashboard/stats"),
          api.get("/recognition-history?limit=8"),
        ]);
        if (!alive) return;
        setStats(s.data);
        setRecent(r.data);
      } catch (_) {}
    };
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const engine = stats?.engine;
  const engineOk = engine?.ready;

  return (
    <div>
      <PageHeader
        title="Command Center"
        subtitle="Live operational overview of the identification network"
      />
      <div className="px-8 pb-10 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatCard testid="stat-users" icon={Users} label="Enrolled identities" value={stats?.total_users ?? "—"} sub="Total in gallery" />
          <StatCard testid="stat-attendance" icon={UserCheck} label="Today's attendance" value={stats?.today_attendance ?? "—"} accent="#00FF66" sub="Unique matches" />
          <StatCard testid="stat-unknown" icon={Warning} label="Unknown faces" value={stats?.total_unknown ?? "—"} accent="#FF3B30" sub="Awaiting review" />
          <StatCard testid="stat-alerts" icon={Bell} label="Unread alerts" value={stats?.unread_alerts ?? "—"} accent="#FFFF00" sub="Since last check" />
          <StatCard testid="stat-cameras" icon={Broadcast} label="Cameras online" value={`${stats?.cameras_online ?? 0}/${stats?.cameras_total ?? 0}`} accent="#00FF66" sub="Active streams" />
          <StatCard testid="stat-engine" icon={Cpu} label="Face engine" value={engineOk ? "ONLINE" : engine?.loading ? "LOADING" : "OFFLINE"} accent={engineOk ? "#00FF66" : engine?.loading ? "#FFFF00" : "#FF3B30"} sub={engine?.model || "—"} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 bg-[#121212] border border-white/10 rounded-md p-5">
            <div className="flex items-center justify-between mb-6">
              <div>
                <div className="text-[10px] tracking-[0.25em] uppercase text-white/40 font-mono">Weekly attendance</div>
                <div className="font-heading text-xl mt-1">Last 7 days</div>
              </div>
              <ChartBar size={20} weight="duotone" color="#00FF66" />
            </div>
            <div style={{ width: "100%", height: 220 }}>
              <ResponsiveContainer>
                <BarChart data={stats?.weekly_attendance || []}>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis dataKey="day" stroke="#71717A" tick={{ fontFamily: "JetBrains Mono", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis stroke="#71717A" tick={{ fontFamily: "JetBrains Mono", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ background: "#0A0A0A", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6, fontFamily: "JetBrains Mono", fontSize: 12 }}
                    cursor={{ fill: "rgba(0,255,102,0.05)" }}
                  />
                  <Bar dataKey="count" fill="#00FF66" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-[#121212] border border-white/10 rounded-md p-5">
            <div className="text-[10px] tracking-[0.25em] uppercase text-white/40 font-mono">Recognition performance</div>
            <div className="mt-6 space-y-6">
              <div>
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-white/50 font-mono uppercase tracking-widest">Avg similarity</span>
                  <span className="font-mono text-2xl text-[#00FF66]">{stats ? (stats.avg_similarity * 100).toFixed(1) + "%" : "—"}</span>
                </div>
                <div className="mt-2 h-1.5 rounded-full bg-white/5 overflow-hidden">
                  <div className="h-full bg-[#00FF66]" style={{ width: `${Math.min(100, (stats?.avg_similarity || 0) * 100)}%` }} />
                </div>
              </div>
              <div>
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-white/50 font-mono uppercase tracking-widest">Match threshold</span>
                  <span className="font-mono text-2xl">{stats ? (stats.match_threshold * 100).toFixed(0) + "%" : "—"}</span>
                </div>
                <div className="mt-2 h-1.5 rounded-full bg-white/5 overflow-hidden">
                  <div className="h-full bg-white/40" style={{ width: `${Math.min(100, (stats?.match_threshold || 0) * 100)}%` }} />
                </div>
              </div>
              <div className="pt-4 border-t border-white/10 flex items-center gap-2 text-xs text-white/50 font-mono">
                <TrendUp size={14} color="#00FF66" />
                {stats?.total_recognitions ?? 0} total recognitions
              </div>
            </div>
          </div>
        </div>

        <div className="bg-[#121212] border border-white/10 rounded-md">
          <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
            <div>
              <div className="text-[10px] tracking-[0.25em] uppercase text-white/40 font-mono">Recent recognitions</div>
              <div className="font-heading text-lg mt-1">Latest matches</div>
            </div>
          </div>
          <div className="divide-y divide-white/5">
            {(recent || []).length === 0 && <div className="px-5 py-8 text-sm text-white/40 font-mono">No recognitions yet.</div>}
            {(recent || []).map((r) => (
              <div key={r.id} className="px-5 py-3 flex items-center gap-4 hover:bg-[#1A1A1A] transition-colors">
                <div className="w-10 h-10 rounded bg-white/5 overflow-hidden border border-white/10">
                  {r.thumbnail_url && <img src={UPLOADS_BASE + r.thumbnail_url} alt="" className="w-full h-full object-cover" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm">{r.name}</div>
                  <div className="text-[11px] text-white/40 font-mono">{r.employee_id || "—"}</div>
                </div>
                <div className="font-mono text-xs text-[#00FF66]">{(r.similarity * 100).toFixed(1)}%</div>
                <div className="font-mono text-[11px] text-white/40 w-40 text-right">{new Date(r.timestamp).toLocaleString()}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
