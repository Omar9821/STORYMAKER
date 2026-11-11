import { useTranslation } from "react-i18next";
import { Header } from "../components/Header";
import { Footer } from "../components/Footer";
import { useLang } from "../context/LangContext";

const CONTACT = process.env.REACT_APP_CONTACT_EMAIL || "contact@hikayati.dz";

// NOTE FOR THE OWNER: these texts are an operational draft that matches how the platform really behaves.
// Have a lawyer review them (data-protection law no. 18-07, consumer protection) before the public launch.
const CONTENT = {
  ar: {
    privacy: {
      title: "سياسة الخصوصية",
      sections: [
        ["من نحن", `حكايتي منصة تُنتج كتب قصص مخصّصة للأطفال. للتواصل بخصوص بياناتك: ${CONTACT}`],
        ["ما البيانات التي نجمعها", "اسم الطفل وعمره وصورته، وما تذكره عن اهتماماته وعائلته، وصور الإخوة أو الحيوان الأليف إن رفعتها، وبيانات التواصل والتوصيل (الاسم، الهاتف، البريد، العنوان، الولاية)."],
        ["لماذا نستعملها", "لكتابة القصة ورسمها وطباعتها وتوصيلها، وللتواصل معك بخصوص طلبك. لا نبيع بياناتك ولا نستعملها للإعلانات."],
        ["مع من نشاركها", "نُرسل النص والصور اللازمة لإنتاج الكتاب إلى مزوّدي ذكاء اصطناعي خارج الجزائر: مزوّد لكتابة القصة (Anthropic) ومزوّد لرسم الصور (fal.ai)، عبر خدمة Emergent. كما تُستضاف البيانات لدى مزوّد استضافة وتخزين. روابط الصور مؤقتة وموقّعة ولا تعمل إلا للمدة اللازمة."],
        ["مدة الاحتفاظ", "صور المرجع (الطفل والإخوة والحيوان) تُحذف بعد التسليم، وتُحذف فوراً عند طلبك. الطلبات التي لا تُؤكَّد خلال 7 أيام تُلغى وتُحذف صورها. نحتفظ بملفات الكتاب الناتج وبيانات الطلب لإعادة الطباعة والدعم والمحاسبة، ويمكنك طلب حذفها في أي وقت."],
        ["حقوقك", `يحق لك الاطلاع على بياناتك وتصحيحها وحذفها وسحب موافقتك. اكتب إلينا على ${CONTACT} وسنرد خلال مدة معقولة.`],
        ["الأطفال", "لا يرفع الصور ويوافق إلا ولي الأمر أو من له صفة قانونية. لا نتواصل مع الأطفال مباشرة."],
        ["الأمان", "الوصول إلى لوحة الإدارة محمي بكلمة مرور وتحديد لمحاولات الدخول، والملفات لا تُعرض إلا بروابط موقّعة ومؤقتة."],
      ],
    },
    terms: {
      title: "الشروط والأحكام",
      sections: [
        ["الخدمة", "نُنتج كتاب قصة رقمياً مخصّصاً لطفلك، وكتاب تلوين اختيارياً، وقد نطبع الكتاب ونوصله حسب الاتفاق."],
        ["الطلب والتأكيد", "بعد إرسال الطلب نتصل بك هاتفياً للتأكيد وتحديد رسوم الشحن. يبدأ الإنتاج بعد التأكيد (أو بعد الدفع الإلكتروني)."],
        ["السعر والدفع", "السعر المعروض بالدينار الجزائري ويشمل الكتاب والإضافات المختارة، وتُضاف رسوم الشحن حسب الولاية. الدفع عند الاستلام أو إلكترونياً."],
        ["المراجعة والجودة", "يُنتج الكتاب بالذكاء الاصطناعي وتراجعه أيدٍ بشرية قبل الإرسال. الشبه بالصورة تقريبي بحكم أسلوب الرسم، وقد نعيد توليد صفحة أو أكثر لتحسين النتيجة."],
        ["الإلغاء والإرجاع", "يمكنك إلغاء الطلب قبل بدء الإنتاج. الكتاب مخصّص لطفلك فلا يُرجع إلا لعيب في الطباعة أو التوصيل أو خطأ منا في البيانات المرسلة."],
        ["حقوق الملكية", "تمنحنا حق استعمال الصور والبيانات لتنفيذ طلبك فقط. الكتاب الناتج للاستعمال الشخصي والعائلي."],
        ["المسؤولية", "نبذل العناية المعقولة في الجودة والتسليم، ولا نتحمل أضراراً غير مباشرة. للاستفسار: " + CONTACT],
      ],
    },
  },
  fr: {
    privacy: {
      title: "Politique de confidentialité",
      sections: [
        ["Qui sommes-nous", `Hikayati produit des livres d'histoires personnalisés pour enfants. Contact pour vos données : ${CONTACT}`],
        ["Données collectées", "Prénom, âge et photo de l'enfant, informations sur ses centres d'intérêt et sa famille, photos de frères/sœurs ou d'un animal si vous les ajoutez, ainsi que vos coordonnées de contact et de livraison."],
        ["Pourquoi", "Écrire, illustrer, imprimer et livrer le livre, et vous contacter au sujet de la commande. Nous ne vendons pas vos données et ne les utilisons pas pour de la publicité."],
        ["Avec qui nous les partageons", "Le texte et les photos nécessaires sont envoyés à des prestataires d'intelligence artificielle situés hors d'Algérie : un prestataire pour l'écriture (Anthropic) et un pour l'illustration (fal.ai), via le service Emergent. Les données sont aussi hébergées chez un prestataire d'hébergement. Les liens vers les photos sont signés et temporaires."],
        ["Durée de conservation", "Les photos de référence (enfant, fratrie, animal) sont supprimées après la livraison, et immédiatement sur demande. Les commandes non confirmées sous 7 jours sont annulées et leurs photos supprimées. Nous conservons les fichiers du livre et les données de commande pour les réimpressions, le support et la comptabilité; vous pouvez demander leur suppression à tout moment."],
        ["Vos droits", `Vous pouvez accéder à vos données, les corriger, les supprimer et retirer votre consentement. Écrivez-nous à ${CONTACT}.`],
        ["Enfants", "Seul le parent ou tuteur légal peut envoyer les photos et donner son accord. Nous ne contactons pas les enfants directement."],
        ["Sécurité", "L'accès à l'administration est protégé par mot de passe et limitation des tentatives; les fichiers ne sont servis que par des liens signés et temporaires."],
      ],
    },
    terms: {
      title: "Conditions générales",
      sections: [
        ["Le service", "Nous produisons un livre d'histoire numérique personnalisé, un cahier de coloriage optionnel, et pouvons imprimer et livrer le livre selon l'accord."],
        ["Commande et confirmation", "Après l'envoi de la commande, nous vous appelons pour confirmer et fixer les frais de livraison. La production démarre après la confirmation (ou le paiement en ligne)."],
        ["Prix et paiement", "Les prix sont en dinars algériens, livre et options choisies inclus; les frais de livraison s'ajoutent selon la wilaya. Paiement à la livraison ou en ligne."],
        ["Relecture et qualité", "Le livre est créé par intelligence artificielle et relu par une personne avant l'envoi. La ressemblance est approximative en raison du style d'illustration; nous pouvons régénérer une ou plusieurs pages pour améliorer le résultat."],
        ["Annulation et retours", "Vous pouvez annuler avant le début de la production. Le livre étant personnalisé, il n'est repris qu'en cas de défaut d'impression ou de livraison, ou d'erreur de notre part."],
        ["Propriété", "Vous nous autorisez à utiliser les photos et données uniquement pour exécuter votre commande. Le livre est destiné à un usage personnel et familial."],
        ["Responsabilité", "Nous apportons un soin raisonnable à la qualité et à la livraison, sans responsabilité pour les dommages indirects. Contact : " + CONTACT],
      ],
    },
  },
  en: {
    privacy: {
      title: "Privacy Policy",
      sections: [
        ["Who we are", `Hikayati produces personalised story books for children. Contact about your data: ${CONTACT}`],
        ["Data we collect", "The child's name, age and photo, details about interests and family, photos of siblings or a pet if you add them, and your contact and delivery details."],
        ["Why we use it", "To write, illustrate, print and deliver the book and to contact you about your order. We do not sell your data or use it for advertising."],
        ["Who receives it", "The text and photos needed to produce the book are sent to AI providers outside Algeria: one for writing (Anthropic) and one for illustration (fal.ai), through the Emergent service. Data is also stored with a hosting provider. Links to photos are signed and temporary."],
        ["Retention", "Reference photos (child, siblings, pet) are deleted after delivery, and immediately on request. Orders not confirmed within 7 days are cancelled and their photos deleted. We keep the book files and order data for reprints, support and accounting; you may ask us to delete them at any time."],
        ["Your rights", `You may access, correct or delete your data and withdraw your consent. Write to ${CONTACT}.`],
        ["Children", "Only a parent or legal guardian may upload photos and give consent. We do not contact children directly."],
        ["Security", "Admin access is password-protected with login throttling, and files are only served through signed, expiring links."],
      ],
    },
    terms: {
      title: "Terms & Conditions",
      sections: [
        ["The service", "We produce a personalised digital story book, an optional coloring book, and may print and deliver the book as agreed."],
        ["Ordering and confirmation", "After you submit an order we call you to confirm it and agree the shipping fee. Production starts after confirmation (or online payment)."],
        ["Price and payment", "Prices are in Algerian dinars and include the book and the options you chose; shipping is added by wilaya. Pay on delivery or online."],
        ["Review and quality", "The book is created with AI and reviewed by a person before shipping. Likeness is approximate because of the illustration style; we may regenerate one or more pages to improve the result."],
        ["Cancellation and returns", "You may cancel before production starts. Because the book is personalised it is only taken back for a printing or delivery defect, or an error on our side."],
        ["Ownership", "You allow us to use the photos and data only to fulfil your order. The book is for personal and family use."],
        ["Liability", "We take reasonable care with quality and delivery and are not liable for indirect damages. Contact: " + CONTACT],
      ],
    },
  },
};

export default function Legal({ kind = "privacy" }) {
  const { lang, dir } = useLang();
  const { t } = useTranslation();
  const doc = (CONTENT[lang] || CONTENT.ar)[kind];
  return (
    <div className="min-h-screen bg-cream" dir={dir}>
      <Header />
      <main className="max-w-3xl mx-auto px-6 py-12" data-testid={`legal-${kind}`}>
        <h1 className="text-3xl font-extrabold text-navy mb-8">{doc.title}</h1>
        <div className="space-y-6">
          {doc.sections.map(([h, p]) => (
            <section key={h} className="soft-card p-6">
              <h2 className="font-bold text-navy mb-2">{h}</h2>
              <p className="text-ink/80 leading-relaxed">{p}</p>
            </section>
          ))}
        </div>
        <p className="text-xs text-ink/40 mt-8">{t("brand")} · 2026</p>
      </main>
      <Footer />
    </div>
  );
}
