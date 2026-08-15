import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Lock, SpinnerGap, BookOpenText } from "@phosphor-icons/react";
import { api } from "../lib/api";

export default function AdminLogin() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      localStorage.setItem("hikayati_token", data.token);
      navigate("/admin");
    } catch (err) {
      toast.error(err.response?.data?.detail || t("common.error"));
      setLoading(false);
    }
  };

  const inputCls = "w-full rounded-2xl border border-border px-4 py-3 outline-none focus:ring-2 focus:ring-terracotta/40";

  return (
    <div className="min-h-screen bg-navy flex items-center justify-center px-4">
      <motion.form initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} onSubmit={submit}
        className="bg-white rounded-3xl p-8 w-full max-w-sm shadow-2xl">
        <div className="flex items-center gap-2 text-terracotta justify-center mb-6">
          <BookOpenText size={30} weight="duotone" />
          <span className="text-2xl font-extrabold text-navy">{t("brand")}</span>
        </div>
        <h1 className="text-xl font-bold text-navy mb-6 flex items-center gap-2"><Lock weight="duotone" /> {t("admin.login")}</h1>
        <label className="block text-sm font-semibold text-ink/70 mb-1">{t("admin.email")}</label>
        <input data-testid="admin-email" type="email" className={`${inputCls} mb-4`} value={email} onChange={(e) => setEmail(e.target.value)} />
        <label className="block text-sm font-semibold text-ink/70 mb-1">{t("admin.password")}</label>
        <input data-testid="admin-password" type="password" className={`${inputCls} mb-6`} value={password} onChange={(e) => setPassword(e.target.value)} />
        <motion.button whileTap={{ scale: 0.95 }} disabled={loading} data-testid="admin-signin"
          className="w-full inline-flex items-center justify-center gap-2 bg-terracotta hover:bg-terracotta-hover text-white font-bold py-3 rounded-full transition-colors">
          {loading ? <SpinnerGap className="animate-spin" /> : null} {t("admin.signin")}
        </motion.button>
      </motion.form>
    </div>
  );
}
