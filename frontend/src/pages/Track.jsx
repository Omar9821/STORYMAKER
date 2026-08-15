import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  MagnifyingGlass, CheckCircle, Circle, SpinnerGap, FilePdf, BookOpen, WarningCircle,
} from "@phosphor-icons/react";
import { Header } from "../components/Header";
import { api, fileUrl } from "../lib/api";
import { useLang } from "../context/LangContext";

const FLOW = ["awaiting_payment", "paid", "generating", "review", "approved", "printing", "shipped", "delivered"];

export default function Track() {
  const { orderId } = useParams();
  const { t } = useTranslation();
  const { dir } = useLang();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [input, setInput] = useState("");

  const load = useCallback(async () => {
    if (!orderId) return;
    try {
      const { data } = await api.get(`/orders/${orderId}`);
      setOrder(data);
      setNotFound(false);
    } catch {
      setNotFound(true);
    }
  }, [orderId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!order) return;
    if (["paid", "generating"].includes(order.status)) {
      const id = setInterval(load, 5000);
      return () => clearInterval(id);
    }
  }, [order, load]);

  const curIdx = order ? FLOW.indexOf(order.status) : -1;
  const failed = order?.status === "failed";

  return (
    <div className="min-h-screen bg-cream">
      <Header />
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-10">
        <h1 className="text-3xl font-extrabold text-navy mb-6">{t("track.title")}</h1>

        {!orderId && (
          <div className="soft-card p-6 flex gap-3">
            <input data-testid="track-input" className="flex-1 rounded-2xl border border-border px-4 py-3 outline-none focus:ring-2 focus:ring-terracotta/40"
              placeholder={t("track.enterId")} value={input} onChange={(e) => setInput(e.target.value)} />
            <button data-testid="track-search" onClick={() => input.trim() && navigate(`/track/${input.trim()}`)}
              className="bg-terracotta text-white font-bold px-5 rounded-2xl inline-flex items-center gap-2">
              <MagnifyingGlass /> {t("track.search")}
            </button>
          </div>
        )}

        {notFound && <p className="soft-card p-6 text-destructive font-medium">{t("track.notFound")}</p>}

        {order && (
          <>
            <div className="soft-card p-6 mb-6">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm text-ink/50">{t("track.orderId")}</span>
                <span className="font-mono text-sm text-ink/70">{order.id.slice(0, 8)}</span>
              </div>
              <div className="flex items-center gap-3 mt-2">
                <span className="text-xl font-extrabold text-navy">{order.child_name}</span>
                {order.story_title && <span className="text-ink/50">— {order.story_title}</span>}
              </div>
              {failed && (
                <p className="mt-3 flex items-center gap-2 text-destructive font-medium" data-testid="track-status">
                  <WarningCircle weight="fill" /> {t("track.st_failed")}
                </p>
              )}
            </div>

            {["paid", "generating"].includes(order.status) && (
              <div className="soft-card p-8 mb-6 flex flex-col items-center text-center" data-testid="generating-box">
                <SpinnerGap size={44} className="animate-spin text-terracotta mb-3" />
                <p className="font-bold text-navy">{t("track.generating")}</p>
              </div>
            )}

            {/* Timeline */}
            {!failed && (
              <div className="soft-card p-6 mb-6" data-testid="track-timeline">
                <div className="space-y-1">
                  {FLOW.slice(1).map((s, i) => {
                    const idx = i + 1;
                    const done = curIdx >= idx;
                    const current = curIdx === idx;
                    return (
                      <div key={s} className="flex items-center gap-3 py-2">
                        {done ? <CheckCircle size={26} weight="fill" className="text-sage" /> : <Circle size={26} className="text-border" />}
                        <span className={`font-semibold ${current ? "text-terracotta" : done ? "text-navy" : "text-ink/40"}`}>
                          {t(`track.st_${s}`)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Book preview */}
            {order.pages?.length > 0 && (
              <div className="soft-card p-6" data-testid="book-preview">
                <div className="flex items-center gap-2 mb-4">
                  <BookOpen weight="duotone" className="text-terracotta" size={26} />
                  <h2 className="text-xl font-bold text-navy">{t("track.preview")}</h2>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {order.cover_path && (
                    <img src={fileUrl(order.cover_path)} alt="cover" className="rounded-xl shadow aspect-[3/4] object-cover" />
                  )}
                  {order.pages.map((p) => (
                    <div key={p.page_number} className="relative">
                      <img src={fileUrl(p.image_path)} alt={`page ${p.page_number}`} className="rounded-xl shadow aspect-[3/4] object-cover" />
                    </div>
                  ))}
                </div>
                {order.pdf_path && (
                  <a href={fileUrl(order.pdf_path)} target="_blank" rel="noreferrer" data-testid="download-pdf"
                    className="mt-5 inline-flex items-center gap-2 bg-navy text-white font-bold px-6 py-3 rounded-full hover:brightness-110 transition-all">
                    <FilePdf weight="duotone" /> {t("track.downloadPdf")}
                  </a>
                )}
                {order.coloring_pdf_path && (
                  <a href={fileUrl(order.coloring_pdf_path)} target="_blank" rel="noreferrer" data-testid="download-coloring"
                    className="mt-5 ms-3 inline-flex items-center gap-2 bg-sage text-white font-bold px-6 py-3 rounded-full hover:brightness-110 transition-all">
                    <FilePdf weight="duotone" /> 🎁 {t("track.downloadColoring")}
                  </a>
                )}
              </div>
            )}

            <SupportBox orderId={order.id} t={t} />
          </>
        )}
      </div>
    </div>
  );
}

const SupportBox = ({ orderId, t }) => {
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  const [list, setList] = useState([]);
  const load = useCallback(() => { api.get(`/tickets/${orderId}`).then(({ data }) => setList(data)).catch(() => {}); }, [orderId]);
  useEffect(() => { load(); }, [load]);
  const send = async () => {
    if (!name.trim() || !msg.trim()) return;
    await api.post("/tickets", { order_id: orderId, name, message: msg });
    setMsg(""); load();
  };
  return (
    <div className="soft-card p-6 mt-6" data-testid="support-box">
      <h2 className="text-lg font-bold text-navy mb-3">{t("x.supportTitle")}</h2>
      <div className="grid gap-2 mb-3">
        <input data-testid="ticket-name" className="rounded-2xl border border-border px-4 py-2.5 outline-none focus:ring-2 focus:ring-terracotta/40" placeholder={t("x.yourName")} value={name} onChange={(e) => setName(e.target.value)} />
        <textarea data-testid="ticket-message" rows={2} className="rounded-2xl border border-border px-4 py-2.5 outline-none focus:ring-2 focus:ring-terracotta/40" placeholder={t("x.yourMessage")} value={msg} onChange={(e) => setMsg(e.target.value)} />
        <button onClick={send} data-testid="ticket-submit" className="self-start bg-terracotta text-white font-bold px-6 py-2.5 rounded-full">{t("x.sendTicket")}</button>
      </div>
      {list.map((tk) => (
        <div key={tk.id} className="border-t border-border/50 py-2 text-sm">
          <p className="text-ink/80">{tk.message}</p>
          {tk.reply && <p className="mt-1 bg-sage/10 rounded-xl p-2 text-ink/80">{t("x.adminReply")}: {tk.reply}</p>}
        </div>
      ))}
    </div>
  );
};

