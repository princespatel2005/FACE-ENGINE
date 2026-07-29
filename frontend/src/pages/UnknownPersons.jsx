import { useEffect, useState } from "react";
import { api, UPLOADS_BASE } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Trash } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function UnknownPersons() {
  const [rows, setRows] = useState([]);
  const load = async () => { const { data } = await api.get("/unknowns"); setRows(data); };
  useEffect(() => { load(); }, []);
  const del = async (id) => {
    if (!window.confirm("Delete this unknown record?")) return;
    try { await api.delete(`/unknowns/${id}`); toast.success("Removed"); load(); } catch { toast.error("Failed"); }
  };
  return (
    <div>
      <PageHeader title="Unknown Faces" subtitle="Captures that failed identity verification" />
      <div className="px-8 py-8">
        {rows.length === 0 ? (
          <div className="bg-[#121212] border border-white/10 rounded-md p-10 text-center text-white/40 font-mono text-sm">
            No unknown faces recorded. When live verification fails, the best frame is saved here for review.
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {rows.map((r) => (
              <div key={r.id} className="bg-[#121212] border border-white/10 rounded-md overflow-hidden group hover:border-[#FF3B30]/40 transition-colors">
                <div className="aspect-square bg-black overflow-hidden">
                  <img src={UPLOADS_BASE + r.image_url} alt="unknown" className="w-full h-full object-cover" />
                </div>
                <div className="p-3 font-mono text-[11px] text-white/60">
                  <div className="flex items-center justify-between">
                    <span className="text-[#FF3B30] uppercase tracking-widest text-[10px]">Unknown</span>
                    <button data-testid={`unknown-delete-${r.id}`} onClick={() => del(r.id)} className="opacity-0 group-hover:opacity-100 transition-opacity text-white/40 hover:text-[#FF3B30]"><Trash size={12} /></button>
                  </div>
                  <div className="mt-2 text-white/50">Cam: {r.camera_id}</div>
                  <div className="text-white/40">Best sim: {(r.similarity * 100).toFixed(1)}%</div>
                  <div className="text-white/40">{new Date(r.timestamp).toLocaleString()}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
