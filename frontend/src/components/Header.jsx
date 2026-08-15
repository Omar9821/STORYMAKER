import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useLang } from "../context/LangContext";
import { BookOpenText, Globe } from "@phosphor-icons/react";
import { motion } from "framer-motion";

const LANGS = [
  { code: "ar", label: "ع" },
  { code: "fr", label: "FR" },
  { code: "en", label: "EN" },
];

export const Header = () => {
  const { t } = useTranslation();
  const { lang, setLang } = useLang();
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-white/70 border-b border-border/40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
        <Link to="/" className="flex items-center gap-2 text-terracotta" data-testid="brand-logo">
          <BookOpenText size={30} weight="duotone" />
          <span className="text-2xl font-extrabold text-navy">{t("brand")}</span>
        </Link>

        <nav className="hidden md:flex items-center gap-7 text-ink/80 font-medium">
          <a href="/#how" className="hover:text-terracotta transition-colors" data-testid="nav-how">{t("nav.how")}</a>
          <a href="/#pricing" className="hover:text-terracotta transition-colors" data-testid="nav-pricing">{t("nav.pricing")}</a>
          <Link to="/track" className="hover:text-terracotta transition-colors" data-testid="nav-track">{t("nav.track")}</Link>
        </nav>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 bg-muted rounded-full p-1" data-testid="lang-switcher">
            <Globe size={16} className="text-muted-foreground ms-1" weight="duotone" />
            {LANGS.map((l) => (
              <button
                key={l.code}
                onClick={() => setLang(l.code)}
                data-testid={`lang-${l.code}`}
                className={`px-2.5 py-1 rounded-full text-sm font-semibold transition-colors ${
                  lang === l.code ? "bg-terracotta text-white" : "text-ink/60 hover:text-ink"
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={() => navigate("/create")}
            data-testid="header-cta"
            className="hidden sm:inline-flex bg-terracotta hover:bg-terracotta-hover text-white font-bold px-5 py-2.5 rounded-full transition-colors"
          >
            {t("nav.start")}
          </motion.button>
        </div>
      </div>
    </header>
  );
};
