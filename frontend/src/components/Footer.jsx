import { useTranslation } from "react-i18next";
import { BookOpenText, Heart } from "@phosphor-icons/react";
import { Link } from "react-router-dom";

export const Footer = () => {
  const { t } = useTranslation();
  return (
    <footer className="bg-navy text-white/90 mt-24">
      <div className="max-w-7xl mx-auto px-6 py-14 grid gap-8 md:grid-cols-3">
        <div>
          <div className="flex items-center gap-2 text-sand mb-3">
            <BookOpenText size={28} weight="duotone" />
            <span className="text-2xl font-extrabold text-white">{t("brand")}</span>
          </div>
          <p className="text-white/60 text-sm max-w-xs">{t("hero.subtitle")}</p>
        </div>
        <div className="flex flex-col gap-2 text-sm">
          <a href="/#how" className="hover:text-sand transition-colors">{t("nav.how")}</a>
          <a href="/#pricing" className="hover:text-sand transition-colors">{t("nav.pricing")}</a>
          <Link to="/track" className="hover:text-sand transition-colors">{t("nav.track")}</Link>
          <Link to="/admin/login" className="hover:text-sand transition-colors">{t("nav.admin")}</Link>
        </div>
        <div className="flex flex-col justify-end text-sm text-white/60">
          <p className="flex items-center gap-1">
            {t("footer.made")} <Heart size={16} weight="fill" className="text-terracotta" />
          </p>
          <p className="mt-2">© 2026 {t("brand")} · {t("footer.rights")}</p>
        </div>
      </div>
    </footer>
  );
};
