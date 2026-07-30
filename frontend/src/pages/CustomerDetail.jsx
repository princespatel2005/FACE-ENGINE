import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, apiError, UPLOADS_BASE } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { toast } from "sonner";
import { Star, Prohibit, User as UserIcon, Receipt, Plus, ArrowLeft, Trash, Coins } from "@phosphor-icons/react";

export default function CustomerDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [u, setU] = useState(null);
  const [purchases, setPurchases] = useState([]);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ product: "", price: 0, quantity: 1, payment_mode: "cash" });
  const [editing, setEditing] = useState(false);
  const [editBuf, setEditBuf] = useState({});

  const load = async () => {
    try {
      const [ru, rp] = await Promise.all([
        api.get(`/users/${id}`),
        api.get(`/purchases?user_id=${id}`),
      ]);
      setU(ru.data);
      setEditBuf({
        name: ru.data.name || "", phone: ru.data.phone || "", email: ru.data.email || "",
        gender: ru.data.gender || "", dob: ru.data.dob || "", address: ru.data.address || "",
        notes: ru.data.notes || "",
      });
      setPurchases(rp.data);
    } catch (e) { toast.error(apiError(e)); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const setWatchlist = async (status) => {
    try { await api.patch(`/users/${id}/watchlist`, { status }); toast.success(`Marked ${status.toUpperCase()}`); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  const saveProfile = async () => {
    try { await api.patch(`/users/${id}`, editBuf); toast.success("Saved"); setEditing(false); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  const addPurchase = async (e) => {
    e.preventDefault();
    try {
      const total = Number(form.price) * Number(form.quantity);
      await api.post("/purchases", {
        user_id: id,
        items: [{ product: form.product, price: Number(form.price), quantity: Number(form.quantity), discount: 0 }],
        total,
        payment_mode: form.payment_mode,
      });
      setForm({ product: "", price: 0, quantity: 1, payment_mode: "cash" });
      setCreating(false);
      load();
    } catch (e) { toast.error(apiError(e)); }
  };

  const delPurchase = async (pid) => {
    if (!window.confirm("Delete this purchase?")) return;
    try { await api.delete(`/purchases/${pid}`); load(); } catch (e) { toast.error(apiError(e)); }
  };

  if (!u) return <div className="p-10 font-mono text-sm text-white/40">Loading…</div>;

  const status = u.watchlist_status || "normal";
  const accent = status === "vip" ? "#FFD400" : status === "blocked" ? "#FF3B30" : "#00FF66";

  return (
    <div>
      <PageHeader
        title={u.name}
        subtitle={`Customer since ${new Date(u.created_at).toLocaleDateString()}`}
        right={
          <button onClick={() => nav(-1)} className="px-3 py-2 rounded-md border border-white/10 text-white/70 font-mono text-xs uppercase tracking-widest hover:bg-white/5 flex items-center gap-1.5">
            <ArrowLeft size={12} /> Back
          </button>
        }
      />

      <div className="px-8 py-8 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: identity */}
        <div className="lg:col-span-1 space-y-4">
          <div className="bg-[#121212] border rounded-md p-6" style={{ borderColor: `${accent}55` }}>
            <div className="flex items-center gap-4">
              <div className="w-24 h-24 rounded-md overflow-hidden bg-white/5 border border-white/10">
                {u.thumbnail_url && <img src={UPLOADS_BASE + u.thumbnail_url} alt="" className="w-full h-full object-cover" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[10px] tracking-[0.25em] uppercase font-mono" style={{ color: accent }}>
                  {status === "vip" ? "★ VIP" : status === "blocked" ? "⚠ BLOCKED" : "Customer"}
                </div>
                <div className="font-heading text-2xl mt-1 truncate">{u.name}</div>
                <div className="text-[11px] font-mono text-white/40 mt-1">{u.phone || u.email || "—"}</div>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-3 gap-2 text-center">
              <div className="p-3 rounded bg-[#0A0A0A] border border-white/5">
                <div className="text-[10px] tracking-[0.2em] uppercase text-white/40 font-mono">Visits</div>
                <div className="font-mono text-xl mt-1">{u.total_visits}</div>
              </div>
              <div className="p-3 rounded bg-[#0A0A0A] border border-white/5">
                <div className="text-[10px] tracking-[0.2em] uppercase text-white/40 font-mono">Spent</div>
                <div className="font-mono text-xl mt-1 text-[#00FF66]">₹{Math.round(u.lifetime_spend || 0).toLocaleString()}</div>
              </div>
              <div className="p-3 rounded bg-[#0A0A0A] border border-white/5">
                <div className="text-[10px] tracking-[0.2em] uppercase text-white/40 font-mono">Loyalty</div>
                <div className="font-mono text-xl mt-1 text-[#FFD400] flex items-center justify-center gap-1"><Coins size={14} /> {u.loyalty_points}</div>
              </div>
            </div>

            <div className="mt-5 flex gap-2">
              <button data-testid="mark-vip-btn" onClick={() => setWatchlist("vip")} className={`flex-1 py-2 rounded-md border font-mono text-[10px] uppercase tracking-widest transition-colors ${status === "vip" ? "border-[#FFD400] text-[#FFD400] bg-[#FFD400]/10" : "border-white/10 text-white/60 hover:bg-white/5"}`}><Star size={12} className="inline mr-1" /> VIP</button>
              <button data-testid="mark-blocked-btn" onClick={() => setWatchlist("blocked")} className={`flex-1 py-2 rounded-md border font-mono text-[10px] uppercase tracking-widest ${status === "blocked" ? "border-[#FF3B30] text-[#FF3B30] bg-[#FF3B30]/10" : "border-white/10 text-white/60 hover:bg-white/5"}`}><Prohibit size={12} className="inline mr-1" /> Block</button>
              <button data-testid="mark-normal-btn" onClick={() => setWatchlist("normal")} className={`flex-1 py-2 rounded-md border font-mono text-[10px] uppercase tracking-widest ${status === "normal" ? "border-white/40 text-white bg-white/5" : "border-white/10 text-white/60 hover:bg-white/5"}`}><UserIcon size={12} className="inline mr-1" /> Reset</button>
            </div>
          </div>

          {/* Profile edit */}
          <div className="bg-[#121212] border border-white/10 rounded-md p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="text-[10px] tracking-[0.25em] uppercase text-white/40 font-mono">Profile</div>
              {!editing ? (
                <button onClick={() => setEditing(true)} className="text-[10px] font-mono uppercase tracking-widest text-[#00FF66] hover:underline">Edit</button>
              ) : (
                <div className="flex gap-2">
                  <button onClick={saveProfile} className="text-[10px] font-mono uppercase tracking-widest text-[#00FF66] hover:underline">Save</button>
                  <button onClick={() => setEditing(false)} className="text-[10px] font-mono uppercase tracking-widest text-white/40 hover:underline">Cancel</button>
                </div>
              )}
            </div>
            {editing ? (
              <div className="space-y-3 font-mono text-sm">
                {["name", "phone", "email", "gender", "dob", "address", "notes"].map((k) => (
                  <label key={k} className="block">
                    <div className="text-[10px] tracking-[0.2em] uppercase text-white/40 mb-1">{k}</div>
                    {k === "notes" || k === "address" ? (
                      <textarea rows={2} value={editBuf[k]} onChange={(e) => setEditBuf({ ...editBuf, [k]: e.target.value })} className="w-full bg-[#0A0A0A] border border-white/10 rounded px-2 py-1.5 outline-none focus:border-[#00FF66]/50" />
                    ) : (
                      <input value={editBuf[k]} onChange={(e) => setEditBuf({ ...editBuf, [k]: e.target.value })} className="w-full bg-[#0A0A0A] border border-white/10 rounded px-2 py-1.5 outline-none focus:border-[#00FF66]/50" />
                    )}
                  </label>
                ))}
              </div>
            ) : (
              <dl className="space-y-3 font-mono text-sm">
                {[["Phone", u.phone], ["Email", u.email], ["Gender", u.gender], ["DOB", u.dob], ["Address", u.address], ["Notes", u.notes], ["Last visit", u.last_visit_at ? new Date(u.last_visit_at).toLocaleString() : "—"]].map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4">
                    <dt className="text-[10px] tracking-[0.2em] uppercase text-white/40 min-w-[90px]">{k}</dt>
                    <dd className="text-white/80 text-right flex-1 break-words">{v || "—"}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
        </div>

        {/* Right: purchases */}
        <div className="lg:col-span-2">
          <div className="bg-[#121212] border border-white/10 rounded-md">
            <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Receipt size={18} weight="duotone" color="#00FF66" />
                <div className="font-heading text-lg">Purchase history</div>
                <div className="text-[11px] font-mono text-white/40">({purchases.length})</div>
              </div>
              <button data-testid="add-purchase-btn" onClick={() => setCreating(!creating)} className="px-3 py-1.5 rounded-md bg-[#00FF66] text-black font-mono text-[10px] uppercase tracking-widest hover:bg-[#00E65C] flex items-center gap-1.5">
                <Plus size={12} weight="bold" /> New purchase
              </button>
            </div>

            {creating && (
              <form onSubmit={addPurchase} className="p-5 border-b border-white/10 grid grid-cols-1 md:grid-cols-5 gap-2">
                <input required data-testid="purchase-product" placeholder="Product" value={form.product} onChange={(e) => setForm({ ...form, product: e.target.value })} className="md:col-span-2 bg-[#0A0A0A] border border-white/10 rounded-md px-3 py-2 text-sm font-mono outline-none focus:border-[#00FF66]/50" />
                <input required type="number" step="0.01" data-testid="purchase-price" placeholder="Price" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} className="bg-[#0A0A0A] border border-white/10 rounded-md px-3 py-2 text-sm font-mono outline-none focus:border-[#00FF66]/50" />
                <input required type="number" data-testid="purchase-qty" placeholder="Qty" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} className="bg-[#0A0A0A] border border-white/10 rounded-md px-3 py-2 text-sm font-mono outline-none focus:border-[#00FF66]/50" />
                <button data-testid="purchase-save" className="py-2 rounded-md bg-[#00FF66] text-black font-mono text-xs uppercase tracking-widest hover:bg-[#00E65C]">Save</button>
              </form>
            )}

            <div className="divide-y divide-white/5">
              {purchases.length === 0 && !creating && <div className="px-5 py-10 text-center text-white/40 font-mono text-sm">No purchases yet.</div>}
              {purchases.map((p) => (
                <div key={p.id} className="px-5 py-3 flex items-center gap-4 hover:bg-[#1A1A1A] transition-colors">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm">{(p.items || []).map((i) => `${i.quantity}× ${i.product}`).join(", ") || "Purchase"}</div>
                    <div className="text-[11px] font-mono text-white/40">{p.invoice_number} · {p.payment_mode}</div>
                  </div>
                  <div className="font-mono text-[#00FF66]">₹{Math.round(p.total).toLocaleString()}</div>
                  <div className="font-mono text-[11px] text-white/40 w-40 text-right">{new Date(p.date).toLocaleString()}</div>
                  <button onClick={() => delPurchase(p.id)} className="p-1.5 rounded text-white/30 hover:text-[#FF3B30] hover:bg-[#FF3B30]/10"><Trash size={12} /></button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
