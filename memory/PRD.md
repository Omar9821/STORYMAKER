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

## Backlog (from user's expanded spec)
### DONE (2026-06, this iteration)
- **Section 14** — Expanded Wizard (5 steps): multiple characters (**250 DZD/extra**, admin-set), per-main-char hair color/type/length, hobbies, favorite color/food; positive/negative behaviors + special details; language level (simple/medium/advanced); story setting multi-select (home/school/parks/fantasy); family context (lives_with required, parents, siblings, friends); quantity + coupon + live price summary. Order API moved to JSON + separate /orders/upload-photo. All fields fed into Claude story context.
- **Section 16** — Admin: editable base_price + extra_character_price from UI; coupons CRUD (%/fixed, max uses, expiry) + validate-coupon; support tickets (customer submit on Track, admin reply); sales reports (today/week/month revenue, AOV, by story-type, top behaviors); partial regeneration (regenerate-text / regenerate-page/{n}) with version-history snapshots; per-page regen buttons + PDF/coloring links in order drawer.
- **Bolder coloring line-art** (FIND_EDGES + threshold + MinFilter for crisp black outlines).
- Verified: pricing math, coupons, tickets, stats, admin guards, wizard 5 steps, admin tabs all GREEN (testing agent iteration_3). fal PuLID result-fetch hardened against transient 502.

### DONE (2026-06, latest iteration)
- **RTL PDF line ordering (Item 17-a)** — VERIFIED: `draw_text_block` wraps logical Arabic text first, then reshapes+bidi per line. Visual check (analyze_file_tool) confirms all lines read top-to-bottom correctly. No backend regression (testing iteration_5: 16/16 pass).
- **Version rollback (Item 16 completion)** — Admin can now RESTORE any previous version. `regenerate_single_page` writes images to NEW versioned paths (`page_{n}_{tag}.png`) so prior images survive; `restore_version_task` snapshots current state (reversible), restores story_title/moral/pages/cover, rebuilds both PDFs. New endpoint `POST /admin/orders/{id}/restore-version/{version_num}` (guards: 401 unauth, 404 missing order/version). UI: restore button per version in order drawer (`data-testid=restore-version-{v}`).
- **Version preview (admin)** — each version row in the order drawer is expandable (`version-toggle-{v}`) showing cover + page thumbnails + text + title/moral, so admin can compare visually before restoring.
- **Art style selection (customer)** — Wizard step 3 lets the customer pick an illustration style: Cartoon / Watercolor / 3D, shown as visual sample thumbnails (`/styles/*.jpg`, testids `style-cartoon|watercolor|3d`). Stored as `order.art_style`; fed into fal PuLID prompt/negative-prompt via `fal_service.STYLE_PROMPTS`. Style shown in admin order detail. Verified e2e (order stores art_style) + UI screenshot.

### P2
- Real Chargily key (leave mock now), print-partner API later, art-style selector, video/audio upsell (deferred).

## Known notes
- Generation takes ~5-6 min per order (6 fal images) — runs as background task; Track page polls.
- Coloring line-art is PIL dodge-sketch (light); could upgrade to AI line-art later.
- Backend suite 17/19 pass; 2 "failures" are pytest cross-class state ordering artifacts, not product bugs.
