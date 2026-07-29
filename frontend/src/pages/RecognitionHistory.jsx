import { useEffect, useState } from "react";
import { api, UPLOADS_BASE } from "@/lib/api";
import PageHeader from "@/components/PageHeader";

export default function RecognitionHistory() {
  const [rows, setRows] = useState([]);
  useEffect(() => { (async () => { const { data } = await api.get("/recognition-history"); setRows(data); })(); }, []);
  return (
    <div>
      <PageHeader title="Recognition Log" subtitle="Every successful match with confidence and camera trace" />
      <div className="px-8 py-8">
        <div className="bg-[#121212] border border-white/10 rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-[0.25em] text-white/40 font-mono border-b border-white/10">
                <th className="px-4 py-3">Identity</th><th className="px-4 py-3">Employee</th><th className="px-4 py-3">Camera</th><th className="px-4 py-3">Similarity</th><th className="px-4 py-3">Frames</th><th className="px-4 py-3">Timestamp</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {rows.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-white/40">No recognitions yet.</td></tr>}
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-white/5 hover:bg-[#1A1A1A]">
                  <td className="px-4 py-3 flex items-center gap-3">
                    <div className="w-8 h-8 rounded bg-white/5 border border-white/10 overflow-hidden">{r.thumbnail_url && <img src={UPLOADS_BASE + r.thumbnail_url} className="w-full h-full object-cover" alt="" />}</div>
                    <span className="text-white text-sm font-sans">{r.name}</span>
                  </td>
                  <td className="px-4 py-3 text-white/70 text-xs">{r.employee_id || "—"}</td>
                  <td className="px-4 py-3 text-white/70 text-xs">{r.camera_id}</td>
                  <td className="px-4 py-3 text-[#00FF66] text-xs">{(r.similarity * 100).toFixed(1)}%</td>
                  <td className="px-4 py-3 text-white/70 text-xs">{r.votes || 1}/{r.frames || 1}</td>
                  <td className="px-4 py-3 text-white/50 text-xs">{new Date(r.timestamp).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
