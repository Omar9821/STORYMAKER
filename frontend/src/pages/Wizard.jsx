import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  ArrowRight, ArrowLeft, UploadSimple, CheckCircle, Sparkle, HeartStraight,
  UsersThree, Translate, Truck, SpinnerGap, Plus, Trash, Target,
} from "@phosphor-icons/react";
import { Header } from "../components/Header";
import { api } from "../lib/api";
import { useLang } from "../context/LangContext";

const TOTAL = 5;
const inputCls = "w-full rounded-2xl border border-border bg-white px-4 py-3 text-ink outline-none focus:ring-2 focus:ring-terracotta/40 transition-shadow";
const label = "block text-sm font-semibold text-ink/70 mb-2";

const uid = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random()));

const emptyChar = (main = false) => ({
  _id: uid(),
  name: "", age: 5, gender: "boy", hair_color: "", hair_type: "", hair_length: "",
  hobbies: "", favorite_color: "", favorite_food: "", relation: "", photo_path: "", is_main: main,
});

export default function Wizard() {
  const { t } = useTranslation();
  const { dir } = useLang();
  const navigate = useNavigate();
  const fileRef = useRef();
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [cfg, setCfg] = useState({ base_price: 3400, extra_character_price: 250 });
  const [photoState, setPhotoState] = useState({ checking: false, ok: false, msg: "", preview: null });
  const [coupon, setCoupon] = useState({ code: "", discount: 0, checked: false });
  const [form, setForm] = useState({
    characters: [emptyChar(true)],
    story_type: "encouragement", positive_behaviors: "", negative_behaviors: "", special_details: "",
    language: "ar", language_level: "simple", art_style: "cartoon", story_setting: [],
    lives_with: "", mother_name: "", mother_age: "", father_name: "", father_age: "", mention_parents: true,
    siblings: [], friends: [], quantity: 1, coupon_code: "",
    customer_name: "", customer_phone: "", customer_email: "", wilaya: "", shipping_address: "", consent: false,
  });

  useEffect(() => { api.get("/config").then(({ data }) => setCfg(data)).catch(() => {}); }, []);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setChar = (i, k, v) => setForm((f) => {
    const c = [...f.characters]; c[i] = { ...c[i], [k]: v }; return { ...f, characters: c };
  });
  const addChar = () => setForm((f) => ({ ...f, characters: [...f.characters, emptyChar(false)] }));
  const removeChar = (i) => setForm((f) => ({ ...f, characters: f.characters.filter((_, idx) => idx !== i) }));
  const togglePlace = (p) => setForm((f) => ({
    ...f, story_setting: f.story_setting.includes(p) ? f.story_setting.filter((x) => x !== p) : [...f.story_setting, p],
  }));
  const addPerson = (key) => setForm((f) => ({ ...f, [key]: [...f[key], { _id: uid(), name: "", age: "", relation: "" }] }));
  const setPerson = (key, i, k, v) => setForm((f) => {
    const arr = [...f[key]]; arr[i] = { ...arr[i], [k]: v }; return { ...f, [key]: arr };
  });

  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;
  const BackArrow = dir === "rtl" ? ArrowRight : ArrowLeft;

  const unit = cfg.base_price + Math.max(0, form.characters.length - 1) * cfg.extra_character_price;
  const subtotal = unit * Math.max(1, form.quantity);
  const total = Math.max(0, subtotal - coupon.discount);

  const handlePhoto = async (file) => {
    if (!file) return;
    setPhotoState({ checking: true, ok: false, msg: "", preview: URL.createObjectURL(file) });
    const fd = new FormData(); fd.append("file", file);
    try {
      const { data } = await api.post("/orders/upload-photo", fd);
      setPhotoState((p) => ({ ...p, checking: false, ok: data.ok, msg: data.message }));
      if (data.ok) setChar(0, "photo_path", data.path);
    } catch { setPhotoState((p) => ({ ...p, checking: false, ok: false, msg: t("common.error") })); }
  };

  const applyCoupon = async () => {
    if (!coupon.code.trim()) return;
    const { data } = await api.post("/orders/validate-coupon", { code: coupon.code, subtotal });
    if (data.valid) { setCoupon((c) => ({ ...c, discount: data.discount, checked: true })); set("coupon_code", coupon.code); toast.success("✓"); }
    else { setCoupon((c) => ({ ...c, discount: 0, checked: true })); toast.error(t("common.error")); }
  };

  const canNext = () => {
    const m = form.characters[0];
    if (step === 1) return m.name.trim() && m.photo_path && photoState.ok;
    if (step === 2) return form.story_type;
    if (step === 3) return form.language;
    if (step === 4) return form.lives_with.trim();
    if (step === 5) return form.customer_name.trim() && form.customer_phone.trim() && form.wilaya.trim() && form.shipping_address.trim() && form.consent;
    return false;
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      const { data } = await api.post("/orders", form);
      navigate(`/track/${data.id}`);
    } catch (e) { toast.error(e.response?.data?.detail || t("common.error")); setSubmitting(false); }
  };

  return (
    <div className="min-h-screen bg-cream">
      <Header />
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-10">
        <div className="flex items-center justify-between mb-2 text-sm text-ink/60 font-semibold">
          <span>{t("wizard.step")} {step} {t("wizard.of")} {TOTAL}</span>
          <span>{Math.round((step / TOTAL) * 100)}%</span>
        </div>
        <div className="h-2 bg-muted rounded-full overflow-hidden mb-8">
          <motion.div className="h-full bg-sage rounded-full" animate={{ width: `${(step / TOTAL) * 100}%` }} transition={{ duration: 0.4 }} />
        </div>

        <div className="soft-card p-6 sm:p-9 min-h-[440px]">
          <AnimatePresence mode="wait">
            <motion.div key={step} initial={{ opacity: 0, x: dir === "rtl" ? -30 : 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: dir === "rtl" ? 30 : -30 }} transition={{ duration: 0.3 }}>

              {step === 1 && (
                <div>
                  <StepHead icon={UsersThree} title={t("x.characters")} />
                  {form.characters.map((c, i) => (
                    <div key={c._id} className={`rounded-2xl border p-4 mb-4 ${i === 0 ? "border-terracotta/40 bg-terracotta/5" : "border-border bg-white"}`}>
                      <div className="flex items-center justify-between mb-3">
                        <span className="font-bold text-navy">{i === 0 ? t("x.mainCharacter") : `${t("x.characters")} ${i + 1} (+${cfg.extra_character_price} DZD)`}</span>
                        {i > 0 && <button onClick={() => removeChar(i)} data-testid={`remove-char-${i}`} className="text-destructive text-sm inline-flex items-center gap-1"><Trash size={16} /> {t("x.removeChar")}</button>}
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div><label className={label}>{t("wizard.childName")}</label>
                          <input data-testid={`char-name-${i}`} className={inputCls} value={c.name} onChange={(e) => setChar(i, "name", e.target.value)} /></div>
                        <div><label className={label}>{t("wizard.childGender")}</label>
                          <select data-testid={`char-gender-${i}`} className={inputCls} value={c.gender} onChange={(e) => setChar(i, "gender", e.target.value)}>
                            <option value="boy">{t("wizard.boy")}</option><option value="girl">{t("wizard.girl")}</option></select></div>
                      </div>
                      <div className="mt-3"><label className={label}>{t("wizard.childAge")}: {c.age}</label>
                        <input type="range" min="1" max="12" value={c.age} onChange={(e) => setChar(i, "age", Number(e.target.value))} className="w-full accent-terracotta" /></div>
                      {i > 0 && (
                        <div className="mt-3"><label className={label}>{t("x.relation")}</label>
                          <input data-testid={`char-relation-${i}`} className={inputCls} value={c.relation} onChange={(e) => setChar(i, "relation", e.target.value)} /></div>
                      )}
                      {i === 0 && (
                        <>
                          <div className="grid grid-cols-3 gap-2 mt-3">
                            <div><label className={label}>{t("x.hairColor")}</label><input className={inputCls} value={c.hair_color} onChange={(e) => setChar(i, "hair_color", e.target.value)} /></div>
                            <div><label className={label}>{t("x.hairType")}</label><input className={inputCls} value={c.hair_type} onChange={(e) => setChar(i, "hair_type", e.target.value)} /></div>
                            <div><label className={label}>{t("x.hairLength")}</label><input className={inputCls} value={c.hair_length} onChange={(e) => setChar(i, "hair_length", e.target.value)} /></div>
                          </div>
                          <div className="grid grid-cols-3 gap-2 mt-3">
                            <div><label className={label}>{t("x.hobbies")}</label><input className={inputCls} value={c.hobbies} onChange={(e) => setChar(i, "hobbies", e.target.value)} /></div>
                            <div><label className={label}>{t("x.favColor")}</label><input className={inputCls} value={c.favorite_color} onChange={(e) => setChar(i, "favorite_color", e.target.value)} /></div>
                            <div><label className={label}>{t("x.favFood")}</label><input className={inputCls} value={c.favorite_food} onChange={(e) => setChar(i, "favorite_food", e.target.value)} /></div>
                          </div>
                          <div className="mt-4">
                            <label className={label}>{t("wizard.photo")}</label>
                            <p className="text-xs text-ink/50 mb-2">{t("wizard.photoHint")}</p>
                            <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => handlePhoto(e.target.files[0])} data-testid="photo-input" />
                            <button onClick={() => fileRef.current?.click()} data-testid="photo-dropzone"
                              className="w-full border-2 border-dashed border-terracotta/40 rounded-2xl p-5 bg-white hover:bg-terracotta/10 transition-colors flex flex-col items-center gap-2">
                              {photoState.preview ? <img src={photoState.preview} alt="" className="w-32 h-32 object-cover rounded-xl shadow" /> : <UploadSimple size={36} weight="duotone" className="text-terracotta" />}
                              <span className="text-ink/70 text-sm">{t("wizard.photoUpload")}</span>
                            </button>
                            {photoState.checking && <p className="mt-2 flex items-center gap-2 text-ink/60 text-sm"><SpinnerGap className="animate-spin" /> {t("wizard.photoChecking")}</p>}
                            {!photoState.checking && photoState.msg && <p data-testid="photo-msg" className={`mt-2 flex items-center gap-2 text-sm font-medium ${photoState.ok ? "text-sage" : "text-destructive"}`}>{photoState.ok && <CheckCircle weight="fill" />} {photoState.msg}</p>}
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                  {form.characters.length < 4 && (
                    <button onClick={addChar} data-testid="add-character" className="w-full py-3 rounded-2xl border-2 border-dashed border-sage text-sage font-bold inline-flex items-center justify-center gap-2 hover:bg-sage/10">
                      <Plus /> {t("x.addCharacter")} <span className="text-xs">({t("x.extraCharCost")})</span>
                    </button>
                  )}
                </div>
              )}

              {step === 2 && (
                <div>
                  <StepHead icon={Target} title={t("x.goals")} />
                  <div className="grid gap-3 mb-4">
                    <BigChoice active={form.story_type === "encouragement"} onClick={() => set("story_type", "encouragement")} testid="type-encouragement" icon={Sparkle} title={t("wizard.encouragement")} desc={t("wizard.encouragementD")} />
                    <BigChoice active={form.story_type === "behavior"} onClick={() => set("story_type", "behavior")} testid="type-behavior" icon={HeartStraight} title={t("wizard.behavior")} desc={t("wizard.behaviorD")} />
                  </div>
                  <div className="space-y-3">
                    <div><label className={label}>{t("x.positive")}</label><input data-testid="positive-behaviors" className={inputCls} value={form.positive_behaviors} onChange={(e) => set("positive_behaviors", e.target.value)} /></div>
                    <div><label className={label}>{t("x.negative")}</label><input data-testid="negative-behaviors" className={inputCls} value={form.negative_behaviors} onChange={(e) => set("negative_behaviors", e.target.value)} /></div>
                    <div><label className={label}>{t("x.special")}</label><input data-testid="special-details" className={inputCls} value={form.special_details} onChange={(e) => set("special_details", e.target.value)} /></div>
                  </div>
                </div>
              )}

              {step === 3 && (
                <div>
                  <StepHead icon={Translate} title={t("x.settings")} />
                  <label className={label}>{t("wizard.language")}</label>
                  <div className="grid grid-cols-3 gap-2 mb-4">
                    {[["ar", t("wizard.langAr")], ["fr", t("wizard.langFr")], ["en", t("wizard.langEn")]].map(([v, l]) => (
                      <Choice key={v} active={form.language === v} onClick={() => set("language", v)} testid={`lang-opt-${v}`}>{l}</Choice>))}
                  </div>
                  <label className={label}>{t("x.level")}</label>
                  <div className="grid grid-cols-3 gap-2 mb-4">
                    {[["simple", t("x.simple")], ["medium", t("x.medium")], ["advanced", t("x.advanced")]].map(([v, l]) => (
                      <Choice key={v} active={form.language_level === v} onClick={() => set("language_level", v)} testid={`level-${v}`}>{l}</Choice>))}
                  </div>
                  <label className={label}>{t("x.artStyle")}</label>
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    {[["cartoon", t("x.styleCartoon"), "/styles/cartoon.jpg"], ["watercolor", t("x.styleWatercolor"), "/styles/watercolor.jpg"], ["3d", t("x.style3d"), "/styles/style3d.jpg"]].map(([v, l, img]) => (
                      <button key={v} type="button" onClick={() => set("art_style", v)} data-testid={`style-${v}`}
                        className={`rounded-2xl border-2 overflow-hidden text-center transition-all active:scale-95 ${form.art_style === v ? "border-terracotta ring-2 ring-terracotta/30 shadow-md" : "border-border hover:border-terracotta/40"}`}>
                        <div className="relative aspect-square">
                          <img src={img} alt={l} className="w-full h-full object-cover" />
                          {form.art_style === v && <span className="absolute top-1.5 end-1.5 bg-terracotta text-white rounded-full p-1"><CheckCircle size={16} weight="fill" /></span>}
                        </div>
                        <span className={`block py-2 text-sm font-bold ${form.art_style === v ? "text-terracotta" : "text-ink/70"}`}>{l}</span>
                      </button>))}
                  </div>
                  <label className={label}>{t("x.place")}</label>
                  <div className="grid grid-cols-2 gap-2">
                    {[["home", t("x.home")], ["school", t("x.school")], ["parks", t("x.parks")], ["fantasy", t("x.fantasy")]].map(([v, l]) => (
                      <Choice key={v} active={form.story_setting.includes(v)} onClick={() => togglePlace(v)} testid={`place-${v}`}>{l}</Choice>))}
                  </div>
                </div>
              )}

              {step === 4 && (
                <div>
                  <StepHead icon={UsersThree} title={t("x.family")} />
                  <div><label className={label}>{t("x.livesWith")} *</label><input data-testid="lives-with" className={inputCls} value={form.lives_with} onChange={(e) => set("lives_with", e.target.value)} /></div>
                  <div className="grid grid-cols-2 gap-3 mt-3">
                    <div><label className={label}>{t("x.motherName")}</label><input className={inputCls} value={form.mother_name} onChange={(e) => set("mother_name", e.target.value)} /></div>
                    <div><label className={label}>{t("x.fatherName")}</label><input className={inputCls} value={form.father_name} onChange={(e) => set("father_name", e.target.value)} /></div>
                  </div>
                  <label className="flex items-center gap-2 mt-3 text-sm text-ink/75"><input type="checkbox" className="w-4 h-4 accent-sage" checked={form.mention_parents} onChange={(e) => set("mention_parents", e.target.checked)} /> {t("x.mentionParents")}</label>
                  <PersonList title={t("x.siblings")} list={form.siblings} onAdd={() => addPerson("siblings")} onSet={(i, k, v) => setPerson("siblings", i, k, v)} t={t} testid="sibling" />
                  <PersonList title={t("x.friends")} list={form.friends} onAdd={() => addPerson("friends")} onSet={(i, k, v) => setPerson("friends", i, k, v)} t={t} rel testid="friend" />
                </div>
              )}

              {step === 5 && (
                <div>
                  <StepHead icon={Truck} title={t("wizard.delivery")} />
                  <div className="space-y-3">
                    <div><label className={label}>{t("wizard.customerName")}</label><input data-testid="customer-name" className={inputCls} value={form.customer_name} onChange={(e) => set("customer_name", e.target.value)} /></div>
                    <div className="grid grid-cols-2 gap-3">
                      <div><label className={label}>{t("wizard.phone")}</label><input data-testid="customer-phone" className={inputCls} value={form.customer_phone} onChange={(e) => set("customer_phone", e.target.value)} /></div>
                      <div><label className={label}>{t("wizard.wilaya")}</label><input data-testid="wilaya" className={inputCls} value={form.wilaya} onChange={(e) => set("wilaya", e.target.value)} /></div>
                    </div>
                    <div><label className={label}>{t("wizard.address")}</label><textarea data-testid="address" rows={2} className={inputCls} value={form.shipping_address} onChange={(e) => set("shipping_address", e.target.value)} /></div>
                    <div className="grid grid-cols-2 gap-3">
                      <div><label className={label}>{t("x.quantity")}</label><input type="number" min="1" data-testid="quantity" className={inputCls} value={form.quantity} onChange={(e) => set("quantity", Math.max(1, Number(e.target.value)))} /></div>
                      <div><label className={label}>{t("x.coupon")}</label>
                        <div className="flex gap-2"><input data-testid="coupon-code" className={inputCls} value={coupon.code} onChange={(e) => setCoupon((c) => ({ ...c, code: e.target.value }))} />
                          <button onClick={applyCoupon} data-testid="apply-coupon" className="px-4 rounded-2xl bg-navy text-white font-bold">{t("x.apply")}</button></div></div>
                    </div>
                    {/* summary */}
                    <div className="bg-sand/20 rounded-2xl p-4 text-sm">
                      <div className="flex justify-between"><span>{t("x.summary")}</span><span>{subtotal} DZD</span></div>
                      {coupon.discount > 0 && <div className="flex justify-between text-sage"><span>{t("x.discount")}</span><span>-{coupon.discount} DZD</span></div>}
                      <div className="flex justify-between font-extrabold text-navy text-lg mt-1"><span>{t("x.total")}</span><span data-testid="wizard-total">{total} DZD</span></div>
                    </div>
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

        <div className="flex items-center justify-between mt-6">
          <button onClick={() => setStep((s) => Math.max(1, s - 1))} disabled={step === 1} data-testid="wizard-back" className="inline-flex items-center gap-2 px-6 py-3 rounded-full font-bold text-navy disabled:opacity-30 hover:bg-navy/5 transition-colors"><BackArrow /> {t("wizard.back")}</button>
          {step < TOTAL ? (
            <motion.button whileTap={{ scale: 0.95 }} onClick={() => canNext() && setStep((s) => s + 1)} disabled={!canNext()} data-testid="wizard-next" className="inline-flex items-center gap-2 bg-terracotta hover:bg-terracotta-hover disabled:opacity-40 text-white font-bold px-8 py-3 rounded-full transition-colors">{t("wizard.next")} <Arrow /></motion.button>
          ) : (
            <motion.button whileTap={{ scale: 0.95 }} onClick={submit} disabled={!canNext() || submitting} data-testid="wizard-submit" className="inline-flex items-center gap-2 bg-terracotta hover:bg-terracotta-hover disabled:opacity-40 text-white font-bold px-8 py-3 rounded-full transition-colors">{submitting ? <SpinnerGap className="animate-spin" /> : null} {t("wizard.submit")}</motion.button>
          )}
        </div>
      </div>
    </div>
  );
}

const StepHead = ({ icon: Icon, title }) => (
  <div className="flex items-center gap-3 mb-6">
    <div className="w-11 h-11 rounded-2xl bg-terracotta/10 flex items-center justify-center"><Icon size={26} weight="duotone" className="text-terracotta" /></div>
    <h2 className="text-2xl font-extrabold text-navy">{title}</h2>
  </div>
);

const Choice = ({ active, onClick, children, testid }) => (
  <button onClick={onClick} data-testid={testid} className={`w-full py-3 rounded-2xl font-bold border-2 transition-colors active:scale-95 ${active ? "border-terracotta bg-terracotta/10 text-terracotta" : "border-border bg-white text-ink/70 hover:border-terracotta/40"}`}>{children}</button>
);

const BigChoice = ({ active, onClick, icon: Icon, title, desc, testid }) => (
  <button onClick={onClick} data-testid={testid} className={`w-full text-start p-5 rounded-2xl border-2 flex items-center gap-4 transition-colors active:scale-[0.98] ${active ? "border-terracotta bg-terracotta/10" : "border-border bg-white hover:border-terracotta/40"}`}>
    <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${active ? "bg-terracotta text-white" : "bg-muted text-ink/50"}`}><Icon size={26} weight="duotone" /></div>
    <div><div className="font-bold text-navy">{title}</div><div className="text-sm text-ink/60">{desc}</div></div>
  </button>
);

const PersonList = ({ title, list, onAdd, onSet, t, rel, testid }) => (
  <div className="mt-4">
    <div className="flex items-center justify-between mb-2"><label className={label}>{title}</label>
      <button onClick={onAdd} data-testid={`add-${testid}`} className="text-sage font-bold text-sm">{t("x.addSibling")}</button></div>
    {list.map((p, i) => (
      <div key={p._id} className="grid grid-cols-3 gap-2 mb-2">
        <input placeholder={t("x.name")} className={inputCls} value={p.name} onChange={(e) => onSet(i, "name", e.target.value)} />
        <input placeholder={t("x.age")} className={inputCls} value={p.age} onChange={(e) => onSet(i, "age", e.target.value)} />
        <input placeholder={rel ? t("x.relation") : t("x.age")} className={inputCls} value={rel ? p.relation : ""} onChange={(e) => onSet(i, rel ? "relation" : "age", e.target.value)} disabled={!rel} />
      </div>
    ))}
  </div>
);
