import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  SignOut, Package, Coins, ChartBar, X, ArrowClockwise, CheckCircle, Truck, Printer,
  FilePdf, Trash, BookOpenText, ClockCounterClockwise, TextT, Ticket, Tag, ChartLineUp, CaretDown, MagnifyingGlass, Warning,
} from "@phosphor-icons/react";
import { api, fileUrl } from "../lib/api";

const STATUS_COLORS = {
  awaiting_payment: "bg-muted text-ink/60", paid: "bg-sand/40 text-navy", generating: "bg-terracotta/15 text-terracotta",
  review: "bg-sand/50 text-navy", approved: "bg-sage/25 text-sage", printing: "bg-navy/10 text-navy",
  shipped: "bg-sage/30 text-sage", delivered: "bg-sage text-white", failed: "bg-destructive/15 text-destructive",
};

const STATUS_LIST = ["awaiting_payment", "generating", "review", "approved", "printing", "shipped", "delivered", "failed"];
const BULK_STATUS = ["approved", "printing", "shipped", "delivered"];

export default function AdminDashboard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [tab, setTab] = useState("orders");
  const [stats, setStats] = useState(null);
  const [orders, setOrders] = useState([]);
  const [coupons, setCoupons] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [settings, setSettings] = useState({ base_price: 3400, extra_character_price: 250, coloring_price: 500, coloring_original_price: 2800 });
  const [selected, setSelected] = useState(null);
  const [newCoupon, setNewCoupon] = useState({ code: "", type: "percent", value: 10, max_uses: 0 });
  const [expandedVer, setExpandedVer] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState([]);

  const loadOrders = useCallback(async (sf, sq) => {
    const params = {};
    if (sf) params.status = sf;
    if (sq) params.search = sq;
    const { data } = await api.get("/admin/orders", { params });
    setOrders(data);
  }, []);

  const loadAll = useCallback(async () => {
    try {
      const [s, o, c, tk, st] = await Promise.all([
        api.get("/admin/stats"), api.get("/admin/orders"), api.get("/admin/coupons"),
        api.get("/admin/tickets"), api.get("/admin/settings"),
      ]);
      setStats(s.data); setOrders(o.data); setCoupons(c.data); setTickets(tk.data); setSettings(st.data);
    } catch (e) { if (e.response?.status === 401) navigate("/admin/login"); }
  }, [navigate]);

  useEffect(() => {
    if (!localStorage.getItem("hikayati_token")) { navigate("/admin/login"); return; }
    loadAll();
  }, [loadAll, navigate]);

  useEffect(() => {
    const id = setTimeout(() => { loadOrders(statusFilter, search).catch(() => {}); }, 350);
    return () => clearTimeout(id);
  }, [statusFilter, search, loadOrders]);

  const toggleSelect = (id) => setSelectedIds((p) => p.includes(id) ? p.filter((x) => x !== id) : [...p, id]);
  const toggleSelectAll = () => setSelectedIds((p) => p.length === orders.length ? [] : orders.map((o) => o.id));
  const refreshOrders = async () => { await loadOrders(statusFilter, search); setSelectedIds([]); };
  const delOrder = (id) => act(async () => { await api.delete(`/admin/orders/${id}`); await refreshOrders(); setSelected(null); }, t("x.deleted"));
  const bulkDelete = () => act(async () => { await api.post("/admin/orders/bulk", { order_ids: selectedIds, action: "delete" }); await refreshOrders(); }, t("x.deleted"));
  const bulkStatus = (status) => { if (!status) return; act(async () => { await api.post("/admin/orders/bulk", { order_ids: selectedIds, action: "status", status }); await refreshOrders(); }, status); };

  const openOrder = async (id) => { const { data } = await api.get(`/admin/orders/${id}`); setSelected(data); };
  const act = async (fn, msg) => {
    try { await fn(); toast.success(msg); await loadAll(); if (selected) await openOrder(selected.id); }
    catch (e) { toast.error(e.response?.data?.detail || t("common.error")); }
  };
  const setStatus = (id, status) => act(() => api.post(`/admin/orders/${id}/status`, { status }), status);
  const logout = () => { localStorage.removeItem("hikayati_token"); navigate("/admin/login"); };

  const saveSettings = () => act(() => api.put("/admin/settings", settings), t("x.save"));
  const addCoupon = () => act(() => api.post("/admin/coupons", newCoupon), t("x.addCoupon"));
  const delCoupon = (code) => act(() => api.delete(`/admin/coupons/${code}`), code);
  const replyTicket = (id, reply) => act(() => api.post(`/admin/tickets/${id}/reply`, { reply }), t("x.reply"));

  const TABS = [["orders", t("x.tabOrders"), Package], ["pricing", t("x.tabPricing"), Tag],
    ["tickets", t("x.tabTickets"), Ticket], ["reports", t("x.tabReports"), ChartLineUp]];

  return (
    <div className="min-h-screen bg-cream">
      <header className="bg-navy text-white">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2"><BookOpenText size={26} weight="duotone" className="text-sand" /><span className="font-extrabold text-lg">{t("brand")} · {t("admin.dashboard")}</span></div>
          <button onClick={logout} data-testid="admin-logout" className="inline-flex items-center gap-2 text-white/80 hover:text-white"><SignOut /> {t("admin.logout")}</button>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {/* tabs */}
        <div className="flex gap-2 mb-6 flex-wrap">
          {TABS.map(([k, lbl, Icon]) => (
            <button key={k} onClick={() => setTab(k)} data-testid={`tab-${k}`} className={`inline-flex items-center gap-2 px-4 py-2 rounded-full font-bold transition-colors ${tab === k ? "bg-terracotta text-white" : "bg-white border border-border text-navy hover:bg-terracotta/10"}`}><Icon size={18} weight="duotone" /> {lbl}</button>
          ))}
        </div>

        {tab === "orders" && (
          <div>
            {/* filter bar */}
            <div className="flex flex-wrap items-center gap-3 mb-4">
              <div className="relative flex-1 min-w-[200px]">
                <MagnifyingGlass size={16} className="absolute top-1/2 -translate-y-1/2 start-3 text-ink/40" />
                <input data-testid="orders-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("x.searchPlaceholder")}
                  className="w-full ps-9 pe-3 py-2.5 rounded-full border border-border bg-white outline-none focus:ring-2 focus:ring-terracotta/30 text-sm" />
              </div>
              <select data-testid="orders-status-filter" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                className="py-2.5 px-4 rounded-full border border-border bg-white outline-none focus:ring-2 focus:ring-terracotta/30 text-sm font-semibold text-navy">
                <option value="">{t("x.allStatuses")}</option>
                {STATUS_LIST.map((s) => <option key={s} value={s}>{t(`track.st_${s}`)}</option>)}
              </select>
              <span className="text-xs text-ink/50" data-testid="orders-count">{orders.length}</span>
            </div>

            {/* bulk action bar */}
            {selectedIds.length > 0 && (
              <div className="flex flex-wrap items-center gap-3 mb-3 bg-navy text-white rounded-2xl px-4 py-3" data-testid="bulk-bar">
                <span className="font-bold text-sm">{selectedIds.length} {t("x.selected")}</span>
                <select data-testid="bulk-status-select" defaultValue="" onChange={(e) => { bulkStatus(e.target.value); e.target.value = ""; }}
                  className="py-2 px-3 rounded-full text-navy text-sm font-semibold outline-none">
                  <option value="">{t("x.bulkStatus")}</option>
                  {BULK_STATUS.map((s) => <option key={s} value={s}>{t(`track.st_${s}`)}</option>)}
                </select>
                <button data-testid="bulk-delete-btn" onClick={() => { if (window.confirm(t("x.confirmDeleteMany"))) bulkDelete(); }}
                  className="inline-flex items-center gap-1.5 bg-destructive hover:bg-destructive/90 text-white text-sm font-bold px-3 py-2 rounded-full transition-colors">
                  <Trash size={14} weight="bold" /> {t("x.bulkDelete")}
                </button>
                <button onClick={() => setSelectedIds([])} className="text-white/70 hover:text-white text-sm ms-auto">{t("x.clear")}</button>
              </div>
            )}

            <div className="soft-card overflow-x-auto">
              <table className="w-full text-start" data-testid="orders-table">
                <thead className="bg-muted/60 text-ink/60 text-sm"><tr>
                  <th className="p-4 w-10"><input type="checkbox" data-testid="select-all" checked={orders.length > 0 && selectedIds.length === orders.length} onChange={toggleSelectAll} className="w-4 h-4 accent-terracotta" /></th>
                  <th className="p-4 text-start">{t("admin.child")}</th><th className="p-4 text-start">{t("admin.customer")}</th>
                  <th className="p-4 text-start">{t("track.status")}</th><th className="p-4 text-start">{t("admin.cost")}</th><th className="p-4 text-start">{t("admin.actions")}</th>
                </tr></thead>
                <tbody>
                  {orders.map((o) => (
                    <tr key={o.id} className={`border-t border-border/60 hover:bg-cream/60 ${selectedIds.includes(o.id) ? "bg-terracotta/5" : ""}`}>
                      <td className="p-4"><input type="checkbox" data-testid={`select-${o.id}`} checked={selectedIds.includes(o.id)} onChange={() => toggleSelect(o.id)} className="w-4 h-4 accent-terracotta" /></td>
                      <td className="p-4 font-semibold text-navy">{o.child_name}<span className="block text-xs text-ink/40">{o.language?.toUpperCase()}</span></td>
                      <td className="p-4 text-ink/70 text-sm">{o.customer_name}<span className="block text-xs text-ink/40">{o.wilaya}</span></td>
                      <td className="p-4"><span className={`px-3 py-1 rounded-full text-xs font-bold ${STATUS_COLORS[o.status] || "bg-muted"}`}>{t(`track.st_${o.status}`)}</span></td>
                      <td className="p-4 text-ink/70 text-sm">${o.ai_cost_usd || 0}</td>
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <button onClick={() => openOrder(o.id)} data-testid={`view-order-${o.id}`} className="text-terracotta font-bold hover:underline">{t("admin.view")}</button>
                          <button onClick={() => { if (window.confirm(t("x.confirmDelete"))) delOrder(o.id); }} data-testid={`delete-order-${o.id}`} className="text-destructive/70 hover:text-destructive" title={t("x.delete")}><Trash size={16} weight="bold" /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {orders.length === 0 && <tr><td colSpan={6} className="p-8 text-center text-ink/40">—</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === "pricing" && (
          <div className="grid md:grid-cols-2 gap-6">
            <div className="soft-card p-6" data-testid="settings-card">
              <h3 className="font-bold text-navy mb-4">{t("x.tabPricing")}</h3>
              <label className="block text-sm font-semibold text-ink/70 mb-1">{t("x.basePrice")} (DZD)</label>
              <input type="number" data-testid="base-price" className="w-full rounded-2xl border border-border px-4 py-3 mb-3" value={settings.base_price} onChange={(e) => setSettings((s) => ({ ...s, base_price: Number(e.target.value) }))} />
              <label className="block text-sm font-semibold text-ink/70 mb-1">{t("x.extraCharPrice")} (DZD)</label>
              <input type="number" data-testid="extra-price" className="w-full rounded-2xl border border-border px-4 py-3 mb-3" value={settings.extra_character_price} onChange={(e) => setSettings((s) => ({ ...s, extra_character_price: Number(e.target.value) }))} />
              <label className="block text-sm font-semibold text-ink/70 mb-1">{t("x.coloringPrice")}</label>
              <input type="number" data-testid="coloring-price" className="w-full rounded-2xl border border-border px-4 py-3 mb-3" value={settings.coloring_price ?? 500} onChange={(e) => setSettings((s) => ({ ...s, coloring_price: Number(e.target.value) }))} />
              <label className="block text-sm font-semibold text-ink/70 mb-1">{t("x.coloringOrigPrice")}</label>
              <input type="number" data-testid="coloring-orig-price" className="w-full rounded-2xl border border-border px-4 py-3 mb-4" value={settings.coloring_original_price ?? 2800} onChange={(e) => setSettings((s) => ({ ...s, coloring_original_price: Number(e.target.value) }))} />
              <button onClick={saveSettings} data-testid="save-settings" className="bg-terracotta text-white font-bold px-6 py-2.5 rounded-full">{t("x.save")}</button>
            </div>
            <div className="soft-card p-6">
              <h3 className="font-bold text-navy mb-4">{t("pricing.badge")} · {t("x.addCoupon")}</h3>
              <div className="grid grid-cols-2 gap-2 mb-2">
                <input placeholder={t("x.couponCode")} data-testid="coupon-code-input" className="rounded-2xl border border-border px-3 py-2" value={newCoupon.code} onChange={(e) => setNewCoupon((c) => ({ ...c, code: e.target.value }))} />
                <select className="rounded-2xl border border-border px-3 py-2" value={newCoupon.type} onChange={(e) => setNewCoupon((c) => ({ ...c, type: e.target.value }))}><option value="percent">{t("x.percent")}</option><option value="fixed">{t("x.fixed")}</option></select>
                <input type="number" placeholder={t("x.couponValue")} className="rounded-2xl border border-border px-3 py-2" value={newCoupon.value} onChange={(e) => setNewCoupon((c) => ({ ...c, value: Number(e.target.value) }))} />
                <input type="number" placeholder={t("x.maxUses")} className="rounded-2xl border border-border px-3 py-2" value={newCoupon.max_uses} onChange={(e) => setNewCoupon((c) => ({ ...c, max_uses: Number(e.target.value) }))} />
              </div>
              <button onClick={addCoupon} data-testid="add-coupon-btn" className="bg-navy text-white font-bold px-5 py-2 rounded-full mb-4">{t("x.addCoupon")}</button>
              <div className="space-y-2">
                {coupons.filter((c) => c.active).map((c) => (
                  <div key={c.code} className="flex items-center justify-between bg-cream rounded-xl px-4 py-2 text-sm">
                    <span className="font-bold text-navy">{c.code}</span>
                    <span className="text-ink/60">{c.value}{c.type === "percent" ? "%" : " DZD"} · {t("x.uses")}: {c.used_count}/{c.max_uses || "∞"}</span>
                    <button onClick={() => delCoupon(c.code)} data-testid={`del-coupon-${c.code}`} className="text-destructive"><Trash size={16} /></button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {tab === "tickets" && (
          <div className="soft-card p-6" data-testid="tickets-panel">
            {tickets.length === 0 && <p className="text-ink/40">{t("x.noTickets")}</p>}
            {tickets.map((tk) => (
              <div key={tk.id} className="border-b border-border/50 py-4">
                <div className="flex items-center justify-between"><span className="font-bold text-navy">{tk.name} <span className="text-xs text-ink/40">#{tk.order_id?.slice(0, 8)}</span></span>
                  <span className={`text-xs font-bold px-2 py-1 rounded-full ${tk.status === "answered" ? "bg-sage/25 text-sage" : "bg-sand/40 text-navy"}`}>{t(`x.${tk.status}`)}</span></div>
                <p className="text-ink/75 my-2">{tk.message}</p>
                {tk.reply ? <p className="text-sm bg-sage/10 rounded-xl p-3 text-ink/80">{t("x.adminReply")}: {tk.reply}</p> : (
                  <ReplyBox onSend={(r) => replyTicket(tk.id, r)} t={t} testid={tk.id} />
                )}
              </div>
            ))}
          </div>
        )}

        {tab === "reports" && stats && (
          <div className="space-y-6" data-testid="reports-panel">
            <div className="grid sm:grid-cols-4 gap-4">
              <StatCard icon={ChartBar} label={t("x.revToday")} value={`${stats.revenue_today} DZD`} color="text-terracotta" />
              <StatCard icon={ChartBar} label={t("x.revWeek")} value={`${stats.revenue_week} DZD`} color="text-sage" />
              <StatCard icon={ChartBar} label={t("x.revMonth")} value={`${stats.revenue_month} DZD`} color="text-navy" />
              <StatCard icon={Coins} label={t("x.aov")} value={`${stats.avg_order_value} DZD`} color="text-terracotta" />
            </div>
            <div className="grid sm:grid-cols-3 gap-4">
              <StatCard icon={Package} label={t("admin.totalOrders")} value={stats.total_orders} color="text-navy" />
              <StatCard icon={ChartBar} label={t("admin.revenue")} value={`${stats.revenue_dzd} DZD`} color="text-sage" />
              <StatCard icon={Coins} label={t("admin.aiCost")} value={`$${stats.total_ai_cost_usd}`} color="text-terracotta" />
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="soft-card p-5"><h4 className="font-bold text-navy mb-3">{t("x.byType")}</h4>
                {Object.entries(stats.by_type || {}).map(([k, v]) => <div key={k} className="flex justify-between text-sm py-1"><span className="text-ink/70">{k}</span><span className="font-bold">{v}</span></div>)}</div>
              <div className="soft-card p-5"><h4 className="font-bold text-navy mb-3">{t("x.topBehaviors")}</h4>
                {(stats.top_behaviors || []).map(([k, v]) => <div key={k} className="flex justify-between text-sm py-1"><span className="text-ink/70 truncate">{k}</span><span className="font-bold">{v}</span></div>)}
                {(!stats.top_behaviors || stats.top_behaviors.length === 0) && <p className="text-ink/40 text-sm">—</p>}</div>
            </div>
          </div>
        )}
      </div>

      {/* Order detail drawer */}
      {selected && (
        <div className="fixed inset-0 bg-black/40 z-50 flex justify-end" onClick={() => setSelected(null)}>
          <div className="bg-cream w-full max-w-xl h-full overflow-y-auto p-6" onClick={(e) => e.stopPropagation()} data-testid="order-detail">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-xl font-extrabold text-navy">{selected.child_name} · {selected.story_title || ""}</h2>
              <button onClick={() => setSelected(null)} data-testid="close-detail" className="text-ink/50 hover:text-ink"><X size={24} /></button>
            </div>
            <div className="soft-card p-4 mb-4 text-sm space-y-1">
              <Row label={t("admin.customer")} value={`${selected.customer_name} · ${selected.customer_phone}`} />
              <Row label={t("wizard.address")} value={`${selected.shipping_address}, ${selected.wilaya}`} />
              <Row label={t("x.total")} value={`${selected.amount} DZD (${selected.extra_characters || 0}×${selected.extra_character_price || 0})`} />
              <Row label={t("track.status")} value={t(`track.st_${selected.status}`)} />
              <Row label={t("x.payment")} value={selected.payment_status === "cod_pending" ? t("x.payConfirmed") : selected.payment_status === "paid" ? t("x.payPaid") : t("x.payPending")} />
              <Row label={t("admin.aiCost")} value={`$${selected.ai_cost_usd || 0}`} />
              {selected.art_style && <Row label={t("x.artStyle")} value={t(`x.style${selected.art_style === "3d" ? "3d" : selected.art_style.charAt(0).toUpperCase() + selected.art_style.slice(1)}`)} />}
              <Row label={t("x.addColoring")} value={selected.add_coloring ? "✓" : "—"} />
              {selected.avg_similarity != null && <Row label={t("admin.similarity")} value={`${selected.avg_similarity} (MOCK)`} />}
              <Row label={t("admin.refDeleted")} value={selected.reference_photo_deleted ? "✓" : "—"} />
              {selected.versions?.length > 0 && <Row label={t("x.versions")} value={selected.versions.length} />}
            </div>

            <div className="flex flex-wrap gap-2 mb-4">
              <ActBtn onClick={() => setStatus(selected.id, "approved")} icon={CheckCircle} label={t("admin.approve")} testid="act-approve" />
              {!selected.reference_photo_deleted && <>
                <ActBtn onClick={() => act(() => api.post(`/admin/orders/${selected.id}/regenerate`), selected.pages?.length ? t("admin.regenerate") : t("x.generate"))} icon={ArrowClockwise} label={selected.pages?.length ? t("admin.regenerate") : t("x.generate")} testid="act-regenerate" />
                <ActBtn onClick={() => act(() => api.post(`/admin/orders/${selected.id}/regenerate-text`), t("x.regenText"))} icon={TextT} label={t("x.regenText")} testid="act-regen-text" />
              </>}
              <ActBtn onClick={() => setStatus(selected.id, "printing")} icon={Printer} label={t("admin.markPrinting")} testid="act-printing" />
              <ActBtn onClick={() => setStatus(selected.id, "shipped")} icon={Truck} label={t("admin.markShipped")} testid="act-shipped" />
              <ActBtn onClick={() => setStatus(selected.id, "delivered")} icon={CheckCircle} label={t("admin.markDelivered")} testid="act-delivered" />
              {!selected.reference_photo_deleted && <ActBtn onClick={() => act(() => api.delete(`/admin/orders/${selected.id}/reference-photo`), "deleted")} icon={Trash} label={t("admin.deletePhoto")} danger testid="act-delete-photo" />}
              <ActBtn onClick={() => { if (window.confirm(t("x.confirmDelete"))) delOrder(selected.id); }} icon={Trash} label={t("x.delete")} danger testid="act-delete-order" />
            </div>
            {selected.reference_photo_deleted && <p className="text-xs text-ink/50 -mt-2 mb-4 flex items-center gap-1.5"><Warning size={14} weight="fill" className="text-sand" /> {t("x.refDeletedNote")}</p>}

            {(selected.pdf_path || selected.coloring_pdf_path) && (
              <div className="soft-card p-4 mb-4">
                <h3 className="font-bold text-navy mb-2 text-sm">{t("x.downloadPrint")}</h3>
                <div className="flex flex-wrap gap-2">
                  {selected.pdf_path && <a href={fileUrl(selected.pdf_path)} target="_blank" rel="noreferrer" data-testid="admin-pdf" className="inline-flex items-center gap-2 bg-navy text-white font-bold px-5 py-2.5 rounded-full hover:brightness-110"><FilePdf weight="duotone" /> {t("x.storyBook")}</a>}
                  {selected.coloring_pdf_path && <a href={fileUrl(selected.coloring_pdf_path)} target="_blank" rel="noreferrer" data-testid="admin-coloring-pdf" className="inline-flex items-center gap-2 bg-sage text-white font-bold px-5 py-2.5 rounded-full hover:brightness-110"><FilePdf weight="duotone" /> {t("x.coloringBook")}</a>}
                </div>
              </div>
            )}

            {selected.pages?.length > 0 && (
              <div>
                <h3 className="font-bold text-navy mb-3">{t("admin.pages")}</h3>
                <div className="grid grid-cols-3 gap-2">
                  {selected.cover_path && <img src={fileUrl(selected.cover_path)} alt="cover" className="rounded-lg shadow aspect-[3/4] object-cover" />}
                  {selected.pages.map((p) => (
                    <div key={p.page_number} className="relative group">
                      <img src={fileUrl(p.image_path)} alt="" className="rounded-lg shadow aspect-[3/4] object-cover" />
                      <span className={`absolute bottom-1 end-1 text-[10px] font-bold px-1.5 py-0.5 rounded ${p.similarity_ok ? "bg-sage text-white" : "bg-destructive text-white"}`}>{p.similarity_score}</span>
                      <button onClick={() => act(() => api.post(`/admin/orders/${selected.id}/regenerate-page/${p.page_number}`), `${t("x.regenPage")} ${p.page_number}`)} data-testid={`regen-page-${p.page_number}`}
                        className="absolute top-1 start-1 bg-white/90 rounded-full p-1 text-terracotta shadow hover:bg-white" title={t("x.regenPage")}><ArrowClockwise size={14} weight="bold" /></button>
                    </div>
                  ))}
                </div>
                {selected.versions?.length > 0 && (
                  <div className="mt-5">
                    <h4 className="font-bold text-navy mb-2 flex items-center gap-2"><ClockCounterClockwise weight="duotone" /> {t("x.versions")}</h4>
                    {selected.versions.map((v) => (
                      <div key={v.version} className="border-b border-border/50 last:border-0 py-1.5" data-testid={`version-row-${v.version}`}>
                        <div className="flex items-center justify-between gap-3">
                          <button onClick={() => setExpandedVer(expandedVer === v.version ? null : v.version)} data-testid={`version-toggle-${v.version}`}
                            className="text-xs text-navy font-semibold inline-flex items-center gap-1 hover:text-terracotta">
                            <CaretDown size={12} weight="bold" className={`transition-transform ${expandedVer === v.version ? "rotate-180" : ""}`} />
                            {t("x.version")} {v.version} — {new Date(v.timestamp).toLocaleString()}
                          </button>
                          <button onClick={() => act(() => api.post(`/admin/orders/${selected.id}/restore-version/${v.version}`), t("x.restoring"))}
                            data-testid={`restore-version-${v.version}`}
                            className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full bg-terracotta/10 text-terracotta hover:bg-terracotta/20 transition-colors active:scale-95">
                            <ArrowClockwise size={12} weight="bold" /> {t("x.restore")}
                          </button>
                        </div>
                        {expandedVer === v.version && (
                          <div className="mt-2 bg-muted/40 rounded-xl p-3" data-testid={`version-preview-${v.version}`}>
                            {v.story_title && <div className="text-sm font-bold text-navy mb-1">{v.story_title}</div>}
                            {v.story_moral && <div className="text-xs text-ink/60 mb-2 italic">{v.story_moral}</div>}
                            <div className="flex gap-1.5 overflow-x-auto pb-1">
                              {v.cover_path && <img src={fileUrl(v.cover_path)} alt="cover" className="w-16 h-20 object-cover rounded-md shadow shrink-0" />}
                              {(v.pages || []).map((p) => (
                                <div key={p.page_number} className="shrink-0 w-16">
                                  <img src={fileUrl(p.image_path)} alt="" className="w-16 h-20 object-cover rounded-md shadow" />
                                  <p className="text-[9px] text-ink/50 leading-tight mt-0.5 line-clamp-2">{p.text}</p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const StatCard = ({ icon: Icon, label, value, color }) => (
  <div className="soft-card p-6 flex items-center gap-4">
    <div className="w-12 h-12 rounded-2xl bg-muted flex items-center justify-center"><Icon size={26} weight="duotone" className={color} /></div>
    <div><div className="text-sm text-ink/50">{label}</div><div className="text-2xl font-extrabold text-navy">{value}</div></div>
  </div>
);
const Row = ({ label, value }) => (<div className="flex justify-between gap-4"><span className="text-ink/50">{label}</span><span className="font-semibold text-navy text-end">{value}</span></div>);
const ActBtn = ({ onClick, icon: Icon, label, danger, testid }) => (
  <button onClick={onClick} data-testid={testid} className={`inline-flex items-center gap-1.5 text-sm font-bold px-3 py-2 rounded-full transition-colors active:scale-95 ${danger ? "bg-destructive/10 text-destructive hover:bg-destructive/20" : "bg-white border border-border text-navy hover:bg-terracotta/10"}`}><Icon size={16} weight="duotone" /> {label}</button>
);
const ReplyBox = ({ onSend, t, testid }) => {
  const [v, setV] = useState("");
  return (
    <div className="flex gap-2 mt-2">
      <input className="flex-1 rounded-xl border border-border px-3 py-2 text-sm" placeholder={t("x.reply")} value={v} onChange={(e) => setV(e.target.value)} data-testid={`ticket-reply-${testid}`} />
      <button onClick={() => v.trim() && onSend(v)} data-testid={`ticket-send-${testid}`} className="bg-terracotta text-white font-bold px-4 rounded-xl text-sm">{t("x.send")}</button>
    </div>
  );
};
