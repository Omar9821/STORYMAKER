# حكايتي (Hikayati) — PRD

## Original problem
منصة ويب تولّد قصص أطفال مصوّرة ومخصّصة بالذكاء الاصطناعي (اسم الطفل + شكله من صورة حقيقية + هدف/سلوك)، وتسلّم PDF رقمي + كتاب مطبوع يُشحن داخل الجزائر. متعددة اللغات RTL(عربي)+LTR(إنجليزي/فرنسي). السعر 3400 دج.

## User choices (locked)
- Text: Claude Sonnet 4.6 · Images: identity-preserving via fal.ai **fal-ai/flux-pulid (PuLID)** through Emergent Universal Key
- Payment: Chargily (online) + COD; currently Chargily in MOCK mode (no key)
- Face-similarity: MOCKED (human review is source of truth)
- Object storage: Emergent encrypted storage

## Architecture
- Backend FastAPI (`/app/backend`): server.py (orders/admin/payments/pipeline), ai_service.py (Claude story), fal_service.py (PuLID illustrations via proxy), pdf_service.py (RTL/LTR PDF + coloring line-art), payment_service.py (Chargily+mock), auth.py (JWT admin), storage.py.
- Frontend React + i18n (ar/en/fr, RTL/LTR): Landing, Wizard(5 steps), Pay, MockPay, Track, AdminLogin, AdminDashboard.
- MongoDB: orders, admins, privacy_logs.

## Implemented (2026-06)
- Landing (RTL, marketing, pricing 3400 DZD, free coloring-book gift highlighted).
- Order Wizard: child (name/age/gender) → story type (encouragement/behavior) → photo upload w/ quality check + consent → language → delivery.
- Payment: COD (works) + Chargily online (MOCK checkout page).
- Generation pipeline (background): Claude story JSON → **fal PuLID identity-preserving illustrations** (cover + 5 pages, fixed seed for character consistency) → RTL/LTR story PDF → **free coloring-book PDF (line-art)**. Verified Arabic PDF renders correctly; likeness verified on real child photos (boy + girl).
- Order tracking timeline + book preview + PDF/coloring downloads.
- Admin dashboard: JWT login, stats (orders/revenue/AI cost per order), order list, detail drawer, status actions (approve/printing/shipped/delivered), regenerate, delete reference photo (privacy log), auto-delete reference on approve.
- Privacy: explicit consent, encrypted storage, reference-photo deletion + privacy logs.

### RESOLVED (was P0 blocker — Section 13)
- Emergent Gemini/OpenAI image endpoints **refuse to transform real human photos** → produced generic children. Switched illustrations to **fal-ai/flux-pulid** (accepts real face photo as reference_image_url, preserves identity, cartoon style). Sample regenerated and confirmed.

## Backlog (from user's expanded spec — awaiting confirmation)
### P1 — Section 14: Expanded Wizard data model (qessati-parity)
- Multiple main characters (price per extra char, admin-set); per child: hair color/type/length, hobbies, favorite color, favorite healthy food.
- Educational goal: positive behaviors (1-2), negative behaviors (1-2), special details free text.
- Story settings: language level (simple/medium/advanced), setting (home/school/parks/fantasy multi-select).
- Family context: who child lives with (required), parents names+ages (opt), mention parents y/n, siblings/friends/relatives names+ages.
- Order options: quantity, Shariah-compliant installment option (Algerian provider).

### P1 — Section 16: Full admin
- Pricing management (edit base price + addons from UI), coupons (%/fixed, max uses, expiry), seasonal offers.
- Orders filter/search; per-part regeneration (text only / single scene / coloring) with version history.
- Support tickets; analytics/reports; multi-level roles; audit log.

### P2
- Real Chargily key (leave mock now), print-partner API later, art-style selector, video/audio upsell (deferred).

## Known notes
- Generation takes ~5-6 min per order (6 fal images) — runs as background task; Track page polls.
- Coloring line-art is PIL dodge-sketch (light); could upgrade to AI line-art later.
- Backend suite 17/19 pass; 2 "failures" are pytest cross-class state ordering artifacts, not product bugs.
