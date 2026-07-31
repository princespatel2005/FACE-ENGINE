import { useEffect, useState } from "react";
import { api, apiError, UPLOADS_BASE } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Trash, UserPlus, X } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function UnknownPersons() {
  const [rows, setRows] = useState([]);
  const [modal, setModal] = useState(null); // unknown record
  const [form, setForm] = useState({ name: "", phone: "", email: "", gender: "", address: "", notes: "" });
  const [busy, setBusy] = useState(false);

  const load = async () => { const { data } = await api.get("/unknowns"); setRows(data); };
  useEffect(() => { load(); }, []);

  const del = async (id) => {
    if (!window.confirm("Delete this unknown record?")) return;
    try { await api.delete(`/unknowns/${id}`); toast.success("Removed"); load(); } catch { toast.error("Failed"); }
  };

  const register = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/register-from-unknown", { unknown_id: modal.id, ...form });
      toast.success(`${data.name} registered as customer`);
      setModal(null);
      setForm({ name: "", phone: "", email: "", gender: "", address: "", notes: "" });
      load();
    } catch (e2) {
      toast.error(apiError(e2));
    } finally { setBusy(false); }
  };

  return (
    <div>
      <PageHeader title="Unknown Faces" subtitle="Captures that failed identity verification — register them into your customer database" />
      <div className="px-8 py-8">
        {rows.length === 0 ? (
          <div className="bg-[#121212] border border-white/10 rounded-md p-10 text-center text-white/40 font-mono text-sm">
            No unknown faces recorded. When live verification fails, the best frame is saved here for review.
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {rows.map((r) => (
              <div key={r.id} className="bg-[#121212] border border-white/10 rounded-md overflow-hidden group hover:border-[#00FF66]/40 transition-colors">
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
                  <div className="text-white/40 mb-2">{new Date(r.timestamp).toLocaleString()}</div>
                  <button data-testid={`register-unknown-${r.id}`} onClick={() => setModal(r)} className="w-full mt-2 py-1.5 rounded bg-[#00FF66] text-black font-mono text-[10px] uppercase tracking-widest hover:bg-[#00E65C] flex items-center justify-center gap-1">
                    <UserPlus size={12} weight="bold" /> Register
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {modal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={() => setModal(null)}>
          <form onSubmit={register} onClick={(e) => e.stopPropagation()} className="w-full max-w-md bg-[#121212] border border-white/10 rounded-md" data-testid="register-unknown-modal">
            <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
              <div className="font-heading text-lg">Register unknown customer</div>
              <button type="button" onClick={() => setModal(null)} className="text-white/40 hover:text-white"><X size={18} /></button>
            </div>
            <div className="p-5">
              <div className="flex items-center gap-4 mb-4">
                <img src={UPLOADS_BASE + modal.image_url} alt="" className="w-20 h-20 rounded-md object-cover border border-white/10" />
                <div className="text-[11px] font-mono text-white/50">
                  Captured on {modal.camera_id}<br />
                  {new Date(modal.timestamp).toLocaleString()}
                </div>
              </div>
              <div className="space-y-3">
                {[
                  ["name", "Full name *", true],
                  ["phone", "Phone", false],
                  ["email", "Email", false],
                  ["gender", "Gender", false],
                  ["address", "Address", false],
                  ["notes", "Notes", false],
                ].map(([k, l, req]) => (
                  <label key={k} className="block">
                    <div className="text-[10px] tracking-[0.2em] uppercase text-white/40 font-mono mb-1">{l}</div>
                    {k === "notes" || k === "address" ? (
                      <textarea rows={2} required={req} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} className="w-full bg-[#0A0A0A] border border-white/10 rounded px-2 py-1.5 text-sm font-mono outline-none focus:border-[#00FF66]/50" />
                    ) : (
                      <input required={req} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} className="w-full bg-[#0A0A0A] border border-white/10 rounded px-2 py-1.5 text-sm font-mono outline-none focus:border-[#00FF66]/50" data-testid={`reg-unknown-${k}`} />
                    )}
                  </label>
                ))}
              </div>
            </div>
            <div className="px-5 py-4 border-t border-white/10 flex justify-end gap-2">
              <button type="button" onClick={() => setModal(null)} className="px-4 py-2 rounded-md border border-white/10 font-mono text-xs uppercase tracking-widest text-white/70 hover:bg-white/5">Cancel</button>
              <button disabled={busy} data-testid="submit-register-unknown" className="px-4 py-2 rounded-md bg-[#00FF66] text-black font-mono text-xs uppercase tracking-widest hover:bg-[#00E65C] disabled:opacity-40">
                {busy ? "Registering…" : "Register customer"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
