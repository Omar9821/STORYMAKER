import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import Lenis from "lenis";
import {
  Sparkle, UploadSimple, MagicWand, Package, PencilSimpleLine,
  Users, HeartStraight, ShieldCheck, CheckCircle, Star,
} from "@phosphor-icons/react";
import { Header } from "../components/Header";
import { Footer } from "../components/Footer";

const HERO_IMG = "https://images.unsplash.com/photo-1592106680408-e7e63efbc7ba?crop=entropy&cs=srgb&fm=jpg&q=85&w=900";
const TRUST_IMG = "https://images.pexels.com/photos/23224850/pexels-photo-23224850.jpeg?auto=compress&w=800";

const fade = {
  hidden: { opacity: 0, y: 24 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: i * 0.08, duration: 0.5 } }),
};

export default function Landing() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  useEffect(() => {
    const lenis = new Lenis({ duration: 1.1 });
    const raf = (time) => { lenis.raf(time); requestAnimationFrame(raf); };
    const id = requestAnimationFrame(raf);
    return () => { cancelAnimationFrame(id); lenis.destroy(); };
  }, []);

  const steps = [
    { icon: PencilSimpleLine, t: "steps.s1t", d: "steps.s1d", cls: "md:col-span-4 bg-sand/30" },
    { icon: UploadSimple, t: "steps.s2t", d: "steps.s2d", cls: "md:col-span-4 bg-sage/25" },
    { icon: MagicWand, t: "steps.s3t", d: "steps.s3d", cls: "md:col-span-4 bg-terracotta/15" },
    { icon: Package, t: "steps.s4t", d: "steps.s4d", cls: "md:col-span-12 bg-navy/5" },
  ];
  const features = [
    { icon: Users, t: "features.f1t", d: "features.f1d" },
    { icon: Sparkle, t: "features.f2t", d: "features.f2d" },
    { icon: HeartStraight, t: "features.f3t", d: "features.f3d" },
    { icon: ShieldCheck, t: "features.f4t", d: "features.f4d" },
  ];

  return (
    <div className="min-h-screen">
      <Header />

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute -top-20 -end-20 w-96 h-96 glow-yellow rounded-full pointer-events-none" />
        <div className="absolute top-40 -start-20 w-80 h-80 glow-sage rounded-full pointer-events-none" />
        <div className="max-w-7xl mx-auto px-6 pt-16 pb-20 grid lg:grid-cols-12 gap-10 items-center">
          <motion.div initial="hidden" animate="show" variants={fade} className="lg:col-span-7 text-start">
            <span className="inline-flex items-center gap-2 bg-white border border-border rounded-full px-4 py-1.5 text-sm font-semibold text-terracotta shadow-sm">
              <Sparkle size={16} weight="fill" /> {t("hero.badge")}
            </span>
            <h1 className="mt-6 text-4xl sm:text-5xl lg:text-6xl font-extrabold text-navy leading-[1.15] tracking-tight">
              {t("hero.title")}
            </h1>
            <p className="mt-6 text-lg text-ink/70 max-w-xl leading-relaxed">{t("hero.subtitle")}</p>
            <div className="mt-8 flex flex-wrap gap-4">
              <motion.button
                whileTap={{ scale: 0.95 }}
                onClick={() => navigate("/create")}
                data-testid="hero-cta"
                className="bg-terracotta hover:bg-terracotta-hover text-white font-bold text-lg px-8 py-4 rounded-full shadow-lg shadow-terracotta/25 transition-colors"
              >
                {t("hero.cta")}
              </motion.button>
              <a href="#how" className="inline-flex items-center font-bold text-lg px-8 py-4 rounded-full border-2 border-navy/15 text-navy hover:bg-navy/5 transition-colors" data-testid="hero-cta2">
                {t("hero.cta2")}
              </a>
            </div>
            <p className="mt-6 flex items-center gap-2 text-sm text-ink/50">
              <ShieldCheck size={18} weight="duotone" className="text-sage" /> {t("hero.trust")}
            </p>
          </motion.div>

          <motion.div initial={{ opacity: 0, scale: 0.94 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.6 }} className="lg:col-span-5 relative">
            <div className="absolute inset-0 bg-terracotta/10 rounded-[2.5rem] rotate-6" />
            <img src={HERO_IMG} alt="child reading" className="relative rounded-[2.5rem] shadow-2xl w-full object-cover aspect-[4/5] animate-float" />
            <div className="absolute -bottom-5 start-4 soft-card px-5 py-3 flex items-center gap-2">
              <Star size={20} weight="fill" className="text-sand" />
              <span className="font-bold text-navy">{t("common.price")}</span>
            </div>
          </motion.div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="max-w-7xl mx-auto px-6 py-20">
        <h2 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-navy text-center mb-12 tracking-tight">
          {t("steps.title")}
        </h2>
        <div className="grid md:grid-cols-12 gap-5">
          {steps.map((s, i) => (
            <motion.div
              key={i} custom={i} initial="hidden" whileInView="show" viewport={{ once: true }} variants={fade}
              className={`${s.cls} rounded-3xl p-8 hover:-translate-y-1 transition-transform`}
            >
              <s.icon size={40} weight="duotone" className="text-navy mb-4" />
              <h3 className="text-xl font-bold text-navy">{t(s.t)}</h3>
              <p className="mt-2 text-ink/65">{t(s.d)}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="bg-white/60 py-20 border-y border-border/50">
        <div className="max-w-7xl mx-auto px-6">
          <h2 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-navy text-center mb-12 tracking-tight">
            {t("features.title")}
          </h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {features.map((f, i) => (
              <motion.div key={i} custom={i} initial="hidden" whileInView="show" viewport={{ once: true }} variants={fade} className="soft-card p-7 text-start">
                <div className="w-14 h-14 rounded-2xl bg-terracotta/10 flex items-center justify-center mb-4">
                  <f.icon size={30} weight="duotone" className="text-terracotta" />
                </div>
                <h3 className="text-lg font-bold text-navy">{t(f.t)}</h3>
                <p className="mt-2 text-sm text-ink/65">{t(f.d)}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="max-w-5xl mx-auto px-6 py-24">
        <div className="grid lg:grid-cols-2 gap-10 items-center">
          <div className="relative">
            <img src={TRUST_IMG} alt="family reading" className="rounded-[2rem] shadow-xl w-full object-cover aspect-square" />
          </div>
          <div className="soft-card p-10 relative">
            <span className="absolute -top-4 end-8 bg-sage text-white text-sm font-bold px-4 py-1.5 rounded-full">
              {t("pricing.badge")}
            </span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-navy">{t("pricing.title")}</h2>
            <div className="mt-6 flex items-end gap-2">
              <span className="text-6xl font-extrabold text-terracotta">{t("pricing.price")}</span>
              <span className="text-2xl font-bold text-ink/60 mb-2">{t("pricing.currency")}</span>
            </div>
            <p className="text-ink/50">{t("pricing.per")}</p>
            <ul className="mt-6 space-y-3">
              {["i1", "i2", "i3", "i4", "i5"].map((k) => (
                <li key={k} className="flex items-center gap-3 text-ink/80">
                  <CheckCircle size={22} weight="fill" className="text-sage shrink-0" />
                  {t(`pricing.${k}`)}
                </li>
              ))}
            </ul>
            <motion.button
              whileTap={{ scale: 0.95 }} onClick={() => navigate("/create")} data-testid="pricing-cta"
              className="mt-8 w-full bg-terracotta hover:bg-terracotta-hover text-white font-bold text-lg py-4 rounded-full transition-colors"
            >
              {t("pricing.cta")}
            </motion.button>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}
