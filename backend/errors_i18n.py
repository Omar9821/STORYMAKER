"""Localised API error messages (review item L11).

Server messages are written in Arabic. The frontend sends `X-Lang: fr|en|ar` (the app language); for fr/en we
translate the known messages, and every error also carries a stable machine-readable `code`."""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# arabic message -> (code, fr, en)
MESSAGES = {
    "الطلب غير موجود": ("order_not_found", "Commande introuvable", "Order not found"),
    "الطلب قيد المعالجة بالفعل، انتظر حتى ينتهي": ("order_busy", "La commande est déjà en cours de traitement, patientez", "The order is already being processed, please wait"),
    "طلبات كثيرة، حاول لاحقاً": ("rate_limited", "Trop de requêtes, réessayez plus tard", "Too many requests, try again later"),
    "محاولات كثيرة. حاول بعد 15 دقيقة": ("login_locked", "Trop de tentatives. Réessayez dans 15 minutes", "Too many attempts. Try again in 15 minutes"),
    "بيانات الدخول غير صحيحة": ("bad_credentials", "Identifiants incorrects", "Invalid credentials"),
    "الملف ليس صورة صالحة": ("not_image", "Le fichier n'est pas une image valide", "The file is not a valid image"),
    "صيغة الصورة غير مدعومة (JPG أو PNG أو WEBP)": ("bad_format", "Format d'image non pris en charge (JPG, PNG ou WEBP)", "Unsupported image format (JPG, PNG or WEBP)"),
    "كود الخصم غير صالح": ("coupon_invalid", "Code promo invalide", "Invalid coupon code"),
    "الكوبون منتهي أو غير فعال": ("coupon_expired", "Code promo expiré ou inactif", "Coupon expired or inactive"),
    "يجب الموافقة على الشروط": ("consent_required", "Vous devez accepter les conditions", "You must accept the terms"),
    "صورة الطفل مطلوبة": ("photo_required", "La photo de l'enfant est obligatoire", "The child's photo is required"),
    "مسار الصورة غير صالح": ("photo_path_invalid", "Chemin de photo invalide", "Invalid photo path"),
    "الانتقال بين هذه الحالتين غير مسموح": ("status_transition", "Changement de statut non autorisé", "This status change is not allowed"),
    "حالة غير معروفة": ("status_unknown", "Statut inconnu", "Unknown status"),
    "الصفحة غير موجودة": ("page_not_found", "Page introuvable", "Page not found"),
    "رسوم الشحن غير صالحة": ("shipping_invalid", "Frais de livraison invalides", "Invalid shipping fee"),
    "الملف غير موجود": ("file_not_found", "Fichier introuvable", "File not found"),
    "الرابط منتهي أو غير صالح": ("link_expired", "Lien expiré ou invalide", "Link expired or invalid"),
    "تعذر إنشاء رابط الدفع": ("payment_failed", "Impossible de créer le lien de paiement", "Could not create the payment link"),
    "لا توجد قصة جاهزة لهذا الطلب": ("no_story", "Aucune histoire prête pour cette commande", "No story is ready for this order"),
}


def _lang(request: Request) -> str:
    v = (request.headers.get("x-lang") or request.headers.get("accept-language", "ar"))[:2].lower()
    return v if v in ("ar", "fr", "en") else "ar"


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    body = {"detail": detail}
    if isinstance(detail, str):
        hit = MESSAGES.get(detail)
        if hit:
            code, fr, en = hit
            lang = _lang(request)
            body = {"detail": fr if lang == "fr" else en if lang == "en" else detail, "code": code}
    return JSONResponse(body, status_code=exc.status_code, headers=getattr(exc, "headers", None))
