import { useEffect, useState } from "react";
import { api, UPLOADS_BASE } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { MagnifyingGlass, Trash } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Users() {
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/users${search ? `?search=${encodeURIComponent(search)}` : ""}`);
      setRows(data);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const del = async (id) => {
    if (!window.confirm("Delete this user and all embeddings?")) return;
    try { await api.delete(`/users/${id}`); toast.success("User deleted"); load(); }
    catch { toast.error("Failed to delete"); }
  };

  return (
    <div>
      <PageHeader
        title="Enrolled Users"
        subtitle={`${rows.length} identities in the gallery`}
        right={
          <div className="flex items-center gap-2 border border-white/10 bg-[#121212] rounded-md px-3 py-2 focus-within:border-[#00FF66]/50">
            <MagnifyingGlass size={14} className="text-white/40" />
            <input
              data-testid="users-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load()}
              placeholder="Search name, ID, department..."
              className="bg-transparent outline-none text-sm font-mono w-72"
            />
          </div>
        }
      />

      <div className="px-8 py-8">
        <div className="bg-[#121212] border border-white/10 rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-[0.25em] text-white/40 font-mono border-b border-white/10">
                <th className="px-4 py-3">Identity</th>
                <th className="px-4 py-3">Employee ID</th>
                <th className="px-4 py-3">Department</th>
                <th className="px-4 py-3">Embeddings</th>
                <th className="px-4 py-3">Enrolled</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {loading && (<tr><td colSpan={6} className="px-4 py-8 text-center text-white/40">Loading...</td></tr>)}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-white/40">No users yet. Enroll one from the Register page.</td></tr>
              )}
              {rows.map((u) => (
                <tr key={u.id} className="border-b border-white/5 hover:bg-[#1A1A1A] transition-colors">
                  <td className="px-4 py-3 flex items-center gap-3">
                    <div className="w-9 h-9 rounded bg-white/5 overflow-hidden border border-white/10">
                      {u.thumbnail_url && <img src={UPLOADS_BASE + u.thumbnail_url} alt="" className="w-full h-full object-cover" />}
                    </div>
                    <div>
                      <div className="text-white text-sm font-sans">{u.name}</div>
                      <div className="text-[11px] text-white/40">{u.email || u.phone || "—"}</div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-white/70 text-xs">{u.employee_id || "—"}</td>
                  <td className="px-4 py-3 text-white/70 text-xs">{u.department || "—"}</td>
                  <td className="px-4 py-3 text-xs"><span className={u.embeddings_count ? "text-[#00FF66]" : "text-[#FFFF00]"}>{u.embeddings_count}</span></td>
                  <td className="px-4 py-3 text-white/50 text-xs">{new Date(u.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3 text-right">
                    <button data-testid={`user-delete-${u.id}`} onClick={() => del(u.id)} className="p-1.5 rounded text-white/40 hover:text-[#FF3B30] hover:bg-[#FF3B30]/10 transition-colors">
                      <Trash size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
