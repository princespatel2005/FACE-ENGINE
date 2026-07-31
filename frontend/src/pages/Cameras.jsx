import { useEffect, useState } from "react";
import { api, apiError, UPLOADS_BASE } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Plus, VideoCamera, Trash, Play, Stop } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Cameras() {
  const [rows, setRows] = useState([]);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", url: "", type: "rtsp", enabled: true });
  const [cacheBust, setCacheBust] = useState(0);

  const load = async () => {
    try { const { data } = await api.get("/cameras"); setRows(data); }
    catch (e) { toast.error(apiError(e)); }
  };

  useEffect(() => {
    load();
    const iv = setInterval(() => { load(); setCacheBust((n) => n + 1); }, 2500);
    return () => clearInterval(iv);
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/cameras", form);
      setForm({ name: "", url: "", type: "rtsp", enabled: true });
      setCreating(false);
      toast.success("Camera added");
      load();
    } catch (e2) { toast.error(apiError(e2)); }
  };

  const toggle = async (cam) => {
    try { await api.patch(`/cameras/${cam.id}`, { enabled: !cam.enabled }); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this camera?")) return;
    try { await api.delete(`/cameras/${id}`); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  return (
    <div>
      <PageHeader
        title="Camera Management"
        subtitle="RTSP / IP feeds ingested server-side. Snapshots refresh every ~1 second."
        right={
          <button data-testid="add-camera-btn" onClick={() => setCreating(true)} className="px-4 py-2 rounded-md bg-[#00FF66] text-black font-mono text-xs tracking-widest uppercase hover:bg-[#00E65C] transition-colors flex items-center gap-2">
            <Plus size={14} weight="bold" /> Add camera
          </button>
        }
      />

      <div className="px-8 py-8 space-y-6">
        {creating && (
          <form onSubmit={submit} className="bg-[#121212] border border-white/10 rounded-md p-5 grid grid-cols-1 md:grid-cols-4 gap-3" data-testid="camera-form">
            <input required data-testid="camera-name" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="bg-[#0A0A0A] border border-white/10 rounded-md px-3 py-2.5 text-sm font-mono outline-none focus:border-[#00FF66]/50" />
            <input required data-testid="camera-url" placeholder="rtsp://user:pass@ip:554/stream" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} className="md:col-span-2 bg-[#0A0A0A] border border-white/10 rounded-md px-3 py-2.5 text-sm font-mono outline-none focus:border-[#00FF66]/50" />
            <div className="flex gap-2">
              <button data-testid="camera-save" className="flex-1 py-2 rounded-md bg-[#00FF66] text-black font-mono text-xs uppercase tracking-widest hover:bg-[#00E65C]">Save</button>
              <button type="button" onClick={() => setCreating(false)} className="px-3 py-2 rounded-md border border-white/10 font-mono text-xs uppercase tracking-widest text-white/60 hover:bg-white/5">Cancel</button>
            </div>
          </form>
        )}

        {rows.length === 0 ? (
          <div className="bg-[#121212] border border-white/10 rounded-md p-10 text-center">
            <VideoCamera size={40} weight="thin" className="mx-auto text-white/30" />
            <div className="mt-4 font-mono text-sm text-white/50">No cameras yet.</div>
            <div className="text-[11px] text-white/30 mt-1">Add an RTSP or IP camera URL to start streaming into the recognition pipeline.</div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {rows.map((c) => {
              const online = c.status === "running";
              return (
                <div key={c.id} className="bg-[#121212] border border-white/10 rounded-md overflow-hidden">
                  <div className="aspect-video bg-black relative">
                    {online ? (
                      <img src={`${UPLOADS_BASE}/uploads/cameras/${c.id}.jpg?t=${cacheBust}`} alt="" className="w-full h-full object-cover" onError={(e) => e.currentTarget.style.opacity = 0.2} />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-white/30 font-mono text-xs uppercase tracking-widest">
                        {c.status === "error" ? c.error || "Stream error" : c.enabled ? "Connecting..." : "Disabled"}
                      </div>
                    )}
                    <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/60 px-2 py-0.5 rounded font-mono text-[10px] uppercase tracking-[0.25em]">
                      <span className={`inline-block w-1.5 h-1.5 rounded-full ${online ? "bg-[#00FF66] animate-pulse" : "bg-white/30"}`} />
                      {online ? "Live" : c.enabled ? "Idle" : "Off"}
                    </div>
                    {online && <div className="absolute top-2 right-2 bg-black/60 px-2 py-0.5 rounded font-mono text-[10px]">{(c.fps || 0).toFixed(1)} fps</div>}
                  </div>
                  <div className="p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm">{c.name}</div>
                        <div className="text-[11px] text-white/40 font-mono truncate max-w-[220px]">{c.url}</div>
                      </div>
                      <div className="flex items-center gap-1">
                        <button data-testid={`camera-toggle-${c.id}`} onClick={() => toggle(c)} className={`p-1.5 rounded ${c.enabled ? "text-[#FFFF00] hover:bg-white/5" : "text-[#00FF66] hover:bg-white/5"}`}>
                          {c.enabled ? <Stop size={16} /> : <Play size={16} weight="fill" />}
                        </button>
                        <button data-testid={`camera-delete-${c.id}`} onClick={() => del(c.id)} className="p-1.5 rounded text-white/40 hover:text-[#FF3B30] hover:bg-[#FF3B30]/10">
                          <Trash size={14} />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
