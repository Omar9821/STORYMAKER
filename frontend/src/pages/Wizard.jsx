import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  ArrowRight, ArrowLeft, UploadSimple, CheckCircle, Sparkle, HeartStraight,
  Baby, ImageSquare, Translate, Truck, SpinnerGap,
} from "@phosphor-icons/react";
import { Header } from "../components/Header";
import { api } from "../lib/api";
import { useLang } from "../context/LangContext";

const TOTAL = 5;

export default function Wizard() {
  const { t } = useTranslation();
  const { dir } = useLang();
  const navigate = useNavigate();
  const fileRef = useRef();
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [photoState, setPhotoState] = useState({ checking: false, ok: false, msg: "", preview: null });
  const [form, setForm] = useState({
    child_name: "", child_age: 5, child_gender: "boy",
    story_type: "encouragement", behavior_focus: "",
    language: "ar", customer_name: "", customer_phone: "", customer_email: "",
    wilaya: "", shipping_address: "", consent: false, photo: null,
  });

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;
  const BackArrow = dir === "rtl" ? ArrowRight : ArrowLeft;

  const handlePhoto = async (file) => {
    if (!file) return;
    set("photo", file);
    setPhotoState({ checking: true, ok: false, msg: "", preview: URL.createObjectURL(file) });
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post("/orders/check-photo", fd);
      setPhotoState((p) => ({ ...p, checking: false, ok: data.ok, msg: data.message }));
    } catch {
      setPhotoState((p) => ({ ...p, checking: false, ok: false, msg: t("common.error") }));
    }
  };

  const canNext = () => {
    if (step === 1) return form.child_name.trim() && form.child_age;
    if (step === 2) return form.story_type && (form.story_type !== "behavior" || form.behavior_focus.trim());
    if (step === 3) return form.photo && photoState.ok;
    if (step === 4) return form.language;
    if (step === 5) return form.customer_name.trim() && form.customer_phone.trim() && form.wilaya.trim() && form.shipping_address.trim() && form.consent;
    return false;
  };

  const submit = async () => {
    setSubmitting(true);
    const fd = new FormData();
    Object.entries(form).forEach(([k, v]) => {
      if (k === "photo") fd.append("photo", v);
      else fd.append(k, v);
    });
    try {
      const { data } = await api.post("/orders", fd);
      toast.success(t("wizard.title"));
      navigate(`/pay/${data.id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || t("common.error"));
      setSubmitting(false);
    }
  };

  const inputCls = "w-full rounded-2xl border border-border bg-white px-4 py-3 text-ink outline-none focus:ring-2 focus:ring-terracotta/40 transition-shadow";
  const label = "block text-sm font-semibold text-ink/70 mb-2";

  return (
    <div className="min-h-screen bg-cream">
      <Header />
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-10">
        {/* progress */}
        <div className="flex items-center justify-between mb-2 text-sm text-ink/60 font-semibold">
          <span>{t("wizard.step")} {step} {t("wizard.of")} {TOTAL}</span>
          <span>{Math.round((step / TOTAL) * 100)}%</span>
        </div>
        <div className="h-2 bg-muted rounded-full overflow-hidden mb-8">
          <motion.div className="h-full bg-sage rounded-full" animate={{ width: `${(step / TOTAL) * 100}%` }} transition={{ duration: 0.4 }} />
        </div>

        <div className="soft-card p-6 sm:p-9 min-h-[420px]">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, x: dir === "rtl" ? -30 : 30 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: dir === "rtl" ? 30 : -30 }}
              transition={{ duration: 0.3 }}
            >
              {step === 1 && (
                <div>
                  <StepHead icon={Baby} title={t("wizard.childInfo")} />
                  <div className="space-y-5">
                    <div>
                      <label className={label}>{t("wizard.childName")}</label>
                      <input data-testid="child-name" className={inputCls} value={form.child_name} onChange={(e) => set("child_name", e.target.value)} />
                    </div>
                    <div>
                      <label className={label}>{t("wizard.childAge")}: {form.child_age}</label>
                      <input data-testid="child-age" type="range" min="1" max="12" value={form.child_age} onChange={(e) => set("child_age", Number(e.target.value))} className="w-full accent-terracotta" />
                    </div>
                    <div>
                      <label className={label}>{t("wizard.childGender")}</label>
                      <div className="grid grid-cols-2 gap-3">
                        {[["boy", t("wizard.boy")], ["girl", t("wizard.girl")]].map(([v, lbl]) => (
                          <Choice key={v} active={form.child_gender === v} onClick={() => set("child_gender", v)} testid={`gender-${v}`}>{lbl}</Choice>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {step === 2 && (
                <div>
                  <StepHead icon={HeartStraight} title={t("wizard.storyType")} />
                  <div className="grid gap-3">
                    <BigChoice active={form.story_type === "encouragement"} onClick={() => set("story_type", "encouragement")} testid="type-encouragement"
                      icon={Sparkle} title={t("wizard.encouragement")} desc={t("wizard.encouragementD")} />
                    <BigChoice active={form.story_type === "behavior"} onClick={() => set("story_type", "behavior")} testid="type-behavior"
                      icon={HeartStraight} title={t("wizard.behavior")} desc={t("wizard.behaviorD")} />
                  </div>
                  {form.story_type === "behavior" && (
                    <div className="mt-5">
                      <label className={label}>{t("wizard.behaviorFocus")}</label>
                      <input data-testid="behavior-focus" className={inputCls} placeholder={t("wizard.behaviorFocusPh")} value={form.behavior_focus} onChange={(e) => set("behavior_focus", e.target.value)} />
                    </div>
                  )}
                </div>
              )}

              {step === 3 && (
                <div>
                  <StepHead icon={ImageSquare} title={t("wizard.photo")} />
                  <p className="text-sm text-ink/60 mb-4">{t("wizard.photoHint")}</p>
                  <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => handlePhoto(e.target.files[0])} data-testid="photo-input" />
                  <button
                    onClick={() => fileRef.current?.click()} data-testid="photo-dropzone"
                    className="w-full border-2 border-dashed border-terracotta/40 rounded-3xl p-8 bg-terracotta/5 hover:bg-terracotta/10 transition-colors flex flex-col items-center gap-3"
                  >
                    {photoState.preview ? (
                      <img src={photoState.preview} alt="preview" className="w-40 h-40 object-cover rounded-2xl shadow" />
                    ) : (
                      <UploadSimple size={44} weight="duotone" className="text-terracotta" />
                    )}
                    <span className="text-ink/70 font-medium">{t("wizard.photoUpload")}</span>
                  </button>
                  {photoState.checking && (
                    <p className="mt-3 flex items-center gap-2 text-ink/60"><SpinnerGap className="animate-spin" /> {t("wizard.photoChecking")}</p>
                  )}
                  {!photoState.checking && photoState.msg && (
                    <p data-testid="photo-msg" className={`mt-3 flex items-center gap-2 font-medium ${photoState.ok ? "text-sage" : "text-destructive"}`}>
                      {photoState.ok && <CheckCircle weight="fill" />} {photoState.msg}
                    </p>
                  )}
                </div>
              )}

              {step === 4 && (
                <div>
                  <StepHead icon={Translate} title={t("wizard.language")} />
                  <div className="grid gap-3">
                    {[["ar", t("wizard.langAr")], ["fr", t("wizard.langFr")], ["en", t("wizard.langEn")]].map(([v, lbl]) => (
                      <Choice key={v} active={form.language === v} onClick={() => set("language", v)} testid={`lang-opt-${v}`}>{lbl}</Choice>
                    ))}
                  </div>
                </div>
              )}

              {step === 5 && (
                <div>
                  <StepHead icon={Truck} title={t("wizard.delivery")} />
                  <div className="space-y-4">
                    <div><label className={label}>{t("wizard.customerName")}</label>
                      <input data-testid="customer-name" className={inputCls} value={form.customer_name} onChange={(e) => set("customer_name", e.target.value)} /></div>
                    <div className="grid grid-cols-2 gap-3">
                      <div><label className={label}>{t("wizard.phone")}</label>
                        <input data-testid="customer-phone" className={inputCls} value={form.customer_phone} onChange={(e) => set("customer_phone", e.target.value)} /></div>
                      <div><label className={label}>{t("wizard.wilaya")}</label>
                        <input data-testid="wilaya" className={inputCls} value={form.wilaya} onChange={(e) => set("wilaya", e.target.value)} /></div>
                    </div>
                    <div><label className={label}>{t("wizard.email")}</label>
                      <input data-testid="customer-email" className={inputCls} value={form.customer_email} onChange={(e) => set("customer_email", e.target.value)} /></div>
                    <div><label className={label}>{t("wizard.address")}</label>
                      <textarea data-testid="address" rows={2} className={inputCls} value={form.shipping_address} onChange={(e) => set("shipping_address", e.target.value)} /></div>
                    <label className="flex items-start gap-3 bg-sage/10 rounded-2xl p-4 cursor-pointer">
                      <input type="checkbox" data-testid="consent" className="mt-1 w-5 h-5 accent-sage shrink-0" checked={form.consent} onChange={(e) => set("consent", e.target.checked)} />
                      <span className="text-sm text-ink/75 leading-relaxed">{t("wizard.consent")}</span>
                    </label>
                  </div>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* nav buttons */}
        <div className="flex items-center justify-between mt-6">
          <button
            onClick={() => setStep((s) => Math.max(1, s - 1))} disabled={step === 1} data-testid="wizard-back"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-full font-bold text-navy disabled:opacity-30 hover:bg-navy/5 transition-colors"
          >
            <BackArrow /> {t("wizard.back")}
          </button>
          {step < TOTAL ? (
            <motion.button whileTap={{ scale: 0.95 }} onClick={() => canNext() && setStep((s) => s + 1)} disabled={!canNext()} data-testid="wizard-next"
              className="inline-flex items-center gap-2 bg-terracotta hover:bg-terracotta-hover disabled:opacity-40 text-white font-bold px-8 py-3 rounded-full transition-colors">
              {t("wizard.next")} <Arrow />
            </motion.button>
          ) : (
            <motion.button whileTap={{ scale: 0.95 }} onClick={submit} disabled={!canNext() || submitting} data-testid="wizard-submit"
              className="inline-flex items-center gap-2 bg-terracotta hover:bg-terracotta-hover disabled:opacity-40 text-white font-bold px-8 py-3 rounded-full transition-colors">
              {submitting ? <SpinnerGap className="animate-spin" /> : null} {t("wizard.submit")}
            </motion.button>
          )}
        </div>
      </div>
    </div>
  );
}

const StepHead = ({ icon: Icon, title }) => (
  <div className="flex items-center gap-3 mb-6">
    <div className="w-11 h-11 rounded-2xl bg-terracotta/10 flex items-center justify-center">
      <Icon size={26} weight="duotone" className="text-terracotta" />
    </div>
    <h2 className="text-2xl font-extrabold text-navy">{title}</h2>
  </div>
);

const Choice = ({ active, onClick, children, testid }) => (
  <button onClick={onClick} data-testid={testid}
    className={`w-full py-4 rounded-2xl font-bold border-2 transition-colors active:scale-95 ${active ? "border-terracotta bg-terracotta/10 text-terracotta" : "border-border bg-white text-ink/70 hover:border-terracotta/40"}`}>
    {children}
  </button>
);

const BigChoice = ({ active, onClick, icon: Icon, title, desc, testid }) => (
  <button onClick={onClick} data-testid={testid}
    className={`w-full text-start p-5 rounded-2xl border-2 flex items-center gap-4 transition-colors active:scale-[0.98] ${active ? "border-terracotta bg-terracotta/10" : "border-border bg-white hover:border-terracotta/40"}`}>
    <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${active ? "bg-terracotta text-white" : "bg-muted text-ink/50"}`}>
      <Icon size={26} weight="duotone" />
    </div>
    <div>
      <div className="font-bold text-navy">{title}</div>
      <div className="text-sm text-ink/60">{desc}</div>
    </div>
  </button>
);
