import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  SignOut, Package, Coins, ChartBar, X, ArrowClockwise, CheckCircle,
  Truck, Printer, FilePdf, Trash, BookOpenText, ShieldCheck,
} from "@phosphor-icons/react";
import { api, fileUrl } from "../lib/api";

const STATUS_COLORS = {
  awaiting_payment: "bg-muted text-ink/60", paid: "bg-sand/40 text-navy",
  generating: "bg-terracotta/15 text-terracotta", review: "bg-sand/50 text-navy",
  approved: "bg-sage/25 text-sage", printing: "bg-navy/10 text-navy",
  shipped: "bg-sage/30 text-sage", delivered: "bg-sage text-white", failed: "bg-destructive/15 text-destructive",
};

export default function AdminDashboard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [orders, setOrders] = useState([]);
  const [selected, setSelected] = useState(null);

  const loadAll = useCallback(async () => {
    try {
      const [s, o] = await Promise.all([api.get("/admin/stats"), api.get("/admin/orders")]);
      setStats(s.data);
      setOrders(o.data);
    } catch (e) {
      if (e.response?.status === 401) navigate("/admin/login");
    }
  }, [navigate]);

  useEffect(() => {
    if (!localStorage.getItem("hikayati_token")) { navigate("/admin/login"); return; }
    loadAll();
  }, [loadAll, navigate]);

  const openOrder = async (id) => {
    const { data } = await api.get(`/admin/orders/${id}`);
    setSelected(data);
  };

  const act = async (fn, msg) => {
    try { await fn(); toast.success(msg); await loadAll(); if (selected) await openOrder(selected.id); }
    catch (e) { toast.error(e.response?.data?.detail || t("common.error")); }
  };

  const setStatus = (id, status, note) => act(() => api.post(`/admin/orders/${id}/status`, { status, note }), status);

  const logout = () => { localStorage.removeItem("hikayati_token"); navigate("/admin/login"); };

  return (
    <div className="min-h-screen bg-cream">
      <header className="bg-navy text-white">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpenText size={26} weight="duotone" className="text-sand" />
            <span className="font-extrabold text-lg">{t("brand")} · {t("admin.dashboard")}</span>
          </div>
          <button onClick={logout} data-testid="admin-logout" className="inline-flex items-center gap-2 text-white/80 hover:text-white">
            <SignOut /> {t("admin.logout")}
          </button>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        {/* Stats */}
        <div className="grid sm:grid-cols-3 gap-4 mb-8">
          <StatCard icon={Package} label={t("admin.totalOrders")} value={stats?.total_orders ?? "—"} color="text-terracotta" />
          <StatCard icon={ChartBar} label={t("admin.revenue")} value={stats ? `${stats.revenue_dzd} DZD` : "—"} color="text-sage" />
          <StatCard icon={Coins} label={t("admin.aiCost")} value={stats ? `$${stats.total_ai_cost_usd}` : "—"} color="text-navy" />
        </div>

        {/* Orders table */}
        <div className="soft-card overflow-hidden">
          <table className="w-full text-start" data-testid="orders-table">
            <thead className="bg-muted/60 text-ink/60 text-sm">
              <tr>
                <th className="p-4 text-start">{t("admin.child")}</th>
                <th className="p-4 text-start">{t("admin.customer")}</th>
                <th className="p-4 text-start">{t("track.status")}</th>
                <th className="p-4 text-start">{t("admin.cost")}</th>
                <th className="p-4 text-start">{t("admin.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="border-t border-border/60 hover:bg-cream/60">
                  <td className="p-4 font-semibold text-navy">{o.child_name}<span className="block text-xs text-ink/40">{o.language.toUpperCase()}</span></td>
                  <td className="p-4 text-ink/70 text-sm">{o.customer_name}<span className="block text-xs text-ink/40">{o.wilaya}</span></td>
                  <td className="p-4"><span className={`px-3 py-1 rounded-full text-xs font-bold ${STATUS_COLORS[o.status] || "bg-muted"}`}>{t(`track.st_${o.status}`)}</span></td>
                  <td className="p-4 text-ink/70 text-sm">${o.ai_cost_usd || 0}</td>
                  <td className="p-4">
                    <button onClick={() => openOrder(o.id)} data-testid={`view-order-${o.id}`} className="text-terracotta font-bold hover:underline">{t("admin.view")}</button>
                  </td>
                </tr>
              ))}
              {orders.length === 0 && <tr><td colSpan={5} className="p-8 text-center text-ink/40">—</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail modal */}
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
              <Row label={t("track.status")} value={t(`track.st_${selected.status}`)} />
              <Row label={t("admin.aiCost")} value={`$${selected.ai_cost_usd || 0}`} />
              {selected.avg_similarity != null && <Row label={t("admin.similarity")} value={`${selected.avg_similarity} (MOCK)`} />}
              <Row label={t("admin.refDeleted")} value={selected.reference_photo_deleted ? "✓" : "—"} />
            </div>

            {/* Actions */}
            <div className="flex flex-wrap gap-2 mb-5">
              <ActBtn onClick={() => setStatus(selected.id, "approved", "approved by admin")} icon={CheckCircle} label={t("admin.approve")} testid="act-approve" />
              <ActBtn onClick={() => act(() => api.post(`/admin/orders/${selected.id}/regenerate`), "regenerating")} icon={ArrowClockwise} label={t("admin.regenerate")} testid="act-regenerate" />
              <ActBtn onClick={() => setStatus(selected.id, "printing", "sent to printer")} icon={Printer} label={t("admin.markPrinting")} testid="act-printing" />
              <ActBtn onClick={() => setStatus(selected.id, "shipped", "shipped")} icon={Truck} label={t("admin.markShipped")} testid="act-shipped" />
              <ActBtn onClick={() => setStatus(selected.id, "delivered", "digital pdf delivered")} icon={FilePdf} label={t("admin.markDelivered")} testid="act-delivered" />
              <ActBtn onClick={() => act(() => api.delete(`/admin/orders/${selected.id}/reference-photo`), "photo deleted")} icon={Trash} label={t("admin.deletePhoto")} danger testid="act-delete-photo" />
            </div>

            {/* Pages preview */}
            {selected.pages?.length > 0 && (
              <div>
                <h3 className="font-bold text-navy mb-3 flex items-center gap-2"><ShieldCheck weight="duotone" className="text-sage" /> {t("admin.pages")}</h3>
                <div className="grid grid-cols-3 gap-2">
                  {selected.cover_path && <img src={fileUrl(selected.cover_path)} alt="cover" className="rounded-lg shadow aspect-[3/4] object-cover" />}
                  {selected.pages.map((p) => (
                    <div key={p.page_number} className="relative">
                      <img src={fileUrl(p.image_path)} alt="" className="rounded-lg shadow aspect-[3/4] object-cover" />
                      <span className={`absolute bottom-1 end-1 text-[10px] font-bold px-1.5 py-0.5 rounded ${p.similarity_ok ? "bg-sage text-white" : "bg-destructive text-white"}`}>
                        {p.similarity_score}
                      </span>
                    </div>
                  ))}
                </div>
                {selected.pdf_path && (
                  <a href={fileUrl(selected.pdf_path)} target="_blank" rel="noreferrer" data-testid="admin-pdf"
                    className="mt-4 inline-flex items-center gap-2 bg-navy text-white font-bold px-5 py-2.5 rounded-full">
                    <FilePdf weight="duotone" /> PDF
                  </a>
                )}
                {selected.coloring_pdf_path && (
                  <a href={fileUrl(selected.coloring_pdf_path)} target="_blank" rel="noreferrer" data-testid="admin-coloring-pdf"
                    className="mt-4 ms-2 inline-flex items-center gap-2 bg-sage text-white font-bold px-5 py-2.5 rounded-full">
                    <FilePdf weight="duotone" /> 🎁 Coloring
                  </a>
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

const Row = ({ label, value }) => (
  <div className="flex justify-between gap-4"><span className="text-ink/50">{label}</span><span className="font-semibold text-navy text-end">{value}</span></div>
);

const ActBtn = ({ onClick, icon: Icon, label, danger, testid }) => (
  <button onClick={onClick} data-testid={testid}
    className={`inline-flex items-center gap-1.5 text-sm font-bold px-3 py-2 rounded-full transition-colors active:scale-95 ${danger ? "bg-destructive/10 text-destructive hover:bg-destructive/20" : "bg-white border border-border text-navy hover:bg-terracotta/10"}`}>
    <Icon size={16} weight="duotone" /> {label}
  </button>
);
