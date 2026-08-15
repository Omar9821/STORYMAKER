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
- **Story narrative order + Arabic spelling (engine-wide)** — strengthened the Claude `generate_story` prompt so each page's sentences are in correct chronological order (setup→development→ending), the plot flows logically across all 5 pages, and Arabic spelling/spacing/punctuation is flawless. Applies to every future story.
- **Coloring-book engine rewrite** — `make_line_art` now uses adaptive local thresholding + morphological closing → COMPLETE, BOLD, uniform outlines that keep full character bodies AND key background elements (window/plants), no floating/missing parts. `build_coloring_pdf` now adds a page number + "حكايتي" logo badge on every page (matching story pages). Verified via rendered sample + testing_agent 12/12.
- **Admin full order data** — order drawer now shows a `order-input-data` section with all submitted fields (date, age/gender, hobbies, fav colour/food, extra characters, lives-with, positive/negative behaviours, special details, setting, language, moral). Regenerate uses the stored data (no re-entry); each regen is snapshotted to `versions[]` (history).

- **BUG FIX — admin generate/print buttons** (verified by testing_agent 15/15): the child's reference photo was auto-deleted on **approve**, which then blocked "توليد/إعادة التوليد". Moved auto-deletion to **shipped/delivered** only (regen stays available through review & printing). Admin drawer now HIDES generate/regen-text/delete-photo when the photo is already deleted, shows a clear note, and surfaces a prominent **"تحميل وطباعة الكتاب"** section (Story-book + Coloring-book PDF links).
- **Coloring book → optional ADD-ON (upsell)** — replaced the either/or `book_type` with `add_coloring` (bool). Every order is the coloured story (base price); customers can add the coloring book for a discounted **500 DZD (was 2800)** via a highlighted upsell card in the wizard's final step. New setting `coloring_original_price` (2800) alongside `coloring_price` (500), both admin-editable and exposed on `/config`. Coloring PDF download (Track) gated by `add_coloring`.

- **Coloring-only product (500 DZD)** — new `book_type` on orders: `colored` (full colour book, base price) vs `coloring` (B&W line-art book to colour, `coloring_price` default 500, admin-editable). Wizard step 3 shows two priced cards; selecting "coloring" hides the art-style picker. `/config` + admin settings expose/edit `coloring_price`. Extra-character pricing still applies on top. Track page shows line-art previews and only the coloring PDF for coloring orders (hides the colour book). Admin order detail shows book type. Verified via curl (500/3400) + wizard screenshots.

- **PDF full redesign (points 18 & 19 — qessati style)** — rewrote `pdf_service.py`: (1) each internal page is an integrated **card** (rounded illustration on top + text below on a coordinated tint) over a **scene-harmonised gradient** background derived from that page's dominant colour; (2) **playful rounded Arabic typography** via **Lemonada** (static instances Regular=500 / Bold=700) replacing classic Amiri; (3) designed **cover** — child inside a circle with a white ring on a gradient, big Lemonada title, subtitle, "حكايتي" logo badge, decorative stars; (4) **festive ending page** — "النهاية" + moral in a framed card with scattered stars; (5) coloring line art tuned to **medium weight**. Verified visually on the real عمر order.
- **Arabic isolated-form fix** — `_fix_isolated()` maps `<isolated>` presentation forms back to base letters so modern fonts (which omit isolated PF-B glyphs) render standalone Arabic letters instead of empty boxes. This is what unlocked using non-Amiri fonts with reportlab+arabic_reshaper.
- **Rebuild-PDF endpoint** — `POST /admin/orders/{id}/rebuild-pdf` re-applies the current PDF template to existing images with **zero AI cost** (used to refresh عمر with the new design).
- **Form simplification (point 20a)** — removed hair color/type/length fields from the wizard, the `Character` model, and the story prompt (`build_story_context`).
- **Per-character photo (point 20b)** — every character card (main + extras) now has its own photo upload (`photo-dropzone-{i}` / `photo-input-{i}`), stored per-character. NOTE: identity preservation (flux-PuLID) still anchors illustrations on the MAIN child's photo per image; rendering a *second real face* in the same scene needs a multi-subject model (future upgrade).


- **Manual/COD payment only** — online Chargily disabled (pay endpoint returns 400 for non-cod). New lifecycle: wizard submit → order `awaiting_payment`/`pending` (NO auto-generation) → customer sees "order received, we'll call you" (Track `order-received-box`) → admin phones to confirm → admin presses **توليد** (`/admin/orders/{id}/regenerate`) which sets `cod`/`cod_pending` and starts generation. Payment status shown in admin drawer.
- **Order management** — single delete (`DELETE /admin/orders/{id}`), bulk actions (`POST /admin/orders/bulk` with action delete|status), and list filters (`GET /admin/orders?status=&search=` on customer_name/phone/child_name). Admin UI: search box + status dropdown + select-all/per-row checkboxes + bulk bar (change status / delete selected) + per-row & drawer delete buttons. Verified via curl + screenshot.
- **Test data cleanup** — deleted 19 test orders; only the 2 real orders (عمر, محمد) remain.


- **RTL PDF line ordering (Item 17-a)** — VERIFIED: `draw_text_block` wraps logical Arabic text first, then reshapes+bidi per line. Visual check (analyze_file_tool) confirms all lines read top-to-bottom correctly. No backend regression (testing iteration_5: 16/16 pass).
- **Version rollback (Item 16 completion)** — Admin can now RESTORE any previous version. `regenerate_single_page` writes images to NEW versioned paths (`page_{n}_{tag}.png`) so prior images survive; `restore_version_task` snapshots current state (reversible), restores story_title/moral/pages/cover, rebuilds both PDFs. New endpoint `POST /admin/orders/{id}/restore-version/{version_num}` (guards: 401 unauth, 404 missing order/version). UI: restore button per version in order drawer (`data-testid=restore-version-{v}`).
- **Version preview (admin)** — each version row in the order drawer is expandable (`version-toggle-{v}`) showing cover + page thumbnails + text + title/moral, so admin can compare visually before restoring.
- **Art style selection (customer)** — Wizard step 3 lets the customer pick an illustration style: Cartoon / Watercolor / 3D, shown as visual sample thumbnails (`/styles/*.jpg`, testids `style-cartoon|watercolor|3d`). Stored as `order.art_style`; fed into fal PuLID prompt/negative-prompt via `fal_service.STYLE_PROMPTS`. Style shown in admin order detail. Verified e2e (order stores art_style) + UI screenshot.

### DONE (2026-06, fork — two P0 bugs)
- **P0 — Arabic narrative order REVERSED (root cause found & fixed, VERIFIED).** Root cause: `pdf_service.paragraph()` and the title/moral draws applied `shp()` (arabic_reshaper + bidi `get_display`) to the WHOLE paragraph BEFORE `_wrap()` split it into lines. bidi reverses the entire RTL string, so wrapping afterwards placed the END of the text on the first line → sentences read backwards. Fix: added `_wrap_shaped()` which wraps the LOGICAL text into lines first (natural top-to-bottom order), THEN reshapes+bidi each line individually. Callers (story-page paragraph, cover title, ending moral) now pass logical text + `rtl`. Verified via `analyze_file_tool` on a crafted ordinal paragraph (أولاً→سادساً correct) AND on the real محمد order (100% correct chronological flow, page by page). Rebuilt PDFs for both real orders (محمد, محمد) with zero AI cost.
- **P0 — Admin "توليد" generate did nothing / order stuck at `failed` (fixed, VERIFIED).** Root cause: fal PuLID image generation aborted the whole 6-image book on a single transient proxy `503`/timeout, marking the order `failed`. Fix: wrapped `generate_illustration_pulid` in a 3-attempt retry with backoff (skips retry only on hard credit failure). The previously-`failed` عمر order now regenerates end-to-end to `review` with the reference photo preserved. (Photo auto-deletion already limited to shipped/delivered + pages exist — confirmed sound.)

### P2
- Real Chargily key (leave mock now), print-partner API later, art-style selector, video/audio upsell (deferred).

## Known notes
- Generation takes ~5-6 min per order (6 fal images) — runs as background task; Track page polls.
- Coloring line-art is PIL dodge-sketch (light); could upgrade to AI line-art later.
- Backend suite 17/19 pass; 2 "failures" are pytest cross-class state ordering artifacts, not product bugs.
