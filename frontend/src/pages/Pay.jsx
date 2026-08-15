import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { CreditCard, Money, SpinnerGap, ShieldCheck } from "@phosphor-icons/react";
import { Header } from "../components/Header";
import { api } from "../lib/api";

export default function Pay() {
  const { orderId } = useParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [method, setMethod] = useState("online");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get(`/orders/${orderId}`).then(({ data }) => setOrder(data)).catch(() => toast.error(t("track.notFound")));
  }, [orderId, t]);

  const pay = async () => {
    setLoading(true);
    try {
      if (method === "cod") {
        await api.post(`/orders/${orderId}/pay`, { method: "cod" });
        navigate(`/track/${orderId}`);
      } else {
        const { data } = await api.post(`/orders/${orderId}/pay`, { method: "chargily", payment_method: "edahabia" });
        window.location.assign(data.checkout_url);
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || t("common.error"));
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-cream">
      <Header />
      <div className="max-w-lg mx-auto px-4 sm:px-6 py-12">
        <div className="soft-card p-8">
          <h1 className="text-2xl font-extrabold text-navy mb-1">{t("pay.title")}</h1>
          <div className="flex items-baseline gap-2 mb-6">
            <span className="text-sm text-ink/60">{t("pay.amount")}:</span>
            <span className="text-3xl font-extrabold text-terracotta">{order ? order.amount : "3400"}</span>
            <span className="font-bold text-ink/60">{t("pricing.currency")}</span>
          </div>

          <div className="grid gap-3">
            <Option active={method === "online"} onClick={() => setMethod("online")} icon={CreditCard} title={t("pay.online")} desc={t("pay.onlineD")} testid="pay-online" />
            <Option active={method === "cod"} onClick={() => setMethod("cod")} icon={Money} title={t("pay.cod")} desc={t("pay.codD")} testid="pay-cod" />
          </div>

          <motion.button whileTap={{ scale: 0.95 }} onClick={pay} disabled={loading} data-testid="pay-submit"
            className="mt-7 w-full inline-flex items-center justify-center gap-2 bg-terracotta hover:bg-terracotta-hover disabled:opacity-50 text-white font-bold text-lg py-4 rounded-full transition-colors">
            {loading ? <SpinnerGap className="animate-spin" /> : null}
            {method === "cod" ? t("pay.confirm") : t("pay.pay")}
          </motion.button>
          <p className="mt-4 flex items-center justify-center gap-2 text-xs text-ink/50">
            <ShieldCheck size={16} weight="duotone" className="text-sage" /> {t("hero.trust")}
          </p>
        </div>
      </div>
    </div>
  );
}

const Option = ({ active, onClick, icon: Icon, title, desc, testid }) => (
  <button onClick={onClick} data-testid={testid}
    className={`w-full text-start p-4 rounded-2xl border-2 flex items-center gap-4 transition-colors active:scale-[0.98] ${active ? "border-terracotta bg-terracotta/10" : "border-border bg-white hover:border-terracotta/40"}`}>
    <div className={`w-11 h-11 rounded-2xl flex items-center justify-center ${active ? "bg-terracotta text-white" : "bg-muted text-ink/50"}`}>
      <Icon size={24} weight="duotone" />
    </div>
    <div>
      <div className="font-bold text-navy">{title}</div>
      <div className="text-sm text-ink/60">{desc}</div>
    </div>
  </button>
);
