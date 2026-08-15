import { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { CreditCard, SpinnerGap, TestTube } from "@phosphor-icons/react";
import { Header } from "../components/Header";
import { api } from "../lib/api";

export default function MockPay() {
  const [params] = useSearchParams();
  const orderId = params.get("order_id");
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  const confirm = async () => {
    setLoading(true);
    try {
      await api.post(`/payments/mock-confirm/${orderId}`);
      navigate(`/track/${orderId}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || t("common.error"));
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-cream">
      <Header />
      <div className="max-w-md mx-auto px-4 py-16">
        <div className="soft-card p-8 text-center">
          <div className="inline-flex items-center gap-2 bg-sand/30 text-navy px-4 py-1.5 rounded-full text-sm font-bold mb-5">
            <TestTube weight="duotone" /> {t("pay.mockTitle")}
          </div>
          <CreditCard size={56} weight="duotone" className="text-terracotta mx-auto mb-4" />
          <p className="text-ink/70 mb-6">{t("pay.mockD")}</p>
          <motion.button whileTap={{ scale: 0.95 }} onClick={confirm} disabled={loading} data-testid="mock-pay-confirm"
            className="w-full inline-flex items-center justify-center gap-2 bg-sage hover:brightness-95 disabled:opacity-50 text-white font-bold py-4 rounded-full transition-all">
            {loading ? <SpinnerGap className="animate-spin" /> : null} {t("pay.mockPay")}
          </motion.button>
        </div>
      </div>
    </div>
  );
}
