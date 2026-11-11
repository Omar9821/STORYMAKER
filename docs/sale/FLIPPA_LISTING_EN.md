# Flippa listing — copy/paste text

**Listing type:** App / SaaS (pre-revenue, "Starter") — Asking price: see SELLER_GUIDE_AR.md

## Title (no revenue figures allowed)
Personalized Children's Storybook Platform (AR/FR/EN) — AI Illustrations, Coloring Books, Print-Ready PDFs, Full Source Code

## Description
(The first line below is required verbatim by Flippa for listings without revenue.)

This app is being sold on the basis of the potential to generate revenue or traffic.

**What it is.** A complete, working web platform that turns a child's photo and details into a personalized illustrated storybook plus a matching coloring book. Parents fill a short wizard, pay (online or cash on delivery), and receive a print-ready PDF; the owner receives the order in an admin dashboard.

**What is included**
- Full source code (React frontend + FastAPI/Python backend + MongoDB), documented and tested end to end with a local harness (61 automated checks passing at handover).
- Story generation with Claude (structured JSON, validation and retries), in Arabic, French and English with correct RTL layout.
- Face-faithful illustrations via fal.ai (multi-reference, consistent character outfit sheet, automatic fallback and circuit breaker).
- Print-ready PDFs: A5 with 3 mm bleed, 300 dpi, cover spread, page count padded to a multiple of 4. Reshaped Arabic text.
- Coloring-book generator (edge-based line art).
- Order flow with signed expiring file links, order tracking page, coupons, shipping fee, status state machine.
- Admin dashboard: orders, stats, tickets, regenerate/restore versions, cost ledger.
- Persistent job queue with crash recovery and Telegram/webhook alerts; /api/health endpoint.
- Privacy tooling: real file deletion and retention sweeper; privacy and terms pages (templates — see disclosures).
- Pluggable storage (S3/Cloudflare R2, local), Chargily Pay integration (Algerian payments), one-click deploy configs for Render + Netlify, step-by-step deployment guide.

**Typical running cost:** about $7/month hosting (other services have free tiers) plus roughly the per-book cost of the AI APIs (see buyer overview).

**Market angle.** Personalized children's books are a proven product category; this build is localized for Arabic-speaking markets, which are underserved. B2B angles: schools, nurseries, gift shops, print shops.

**Honest disclosures**
- Pre-revenue: no customers, no traffic, no revenue history. Nothing here is a revenue claim.
- The code was built with AI assistance and then reviewed, hardened and tested. Not audited by a third party.
- Payments (Chargily) have been exercised in mock mode; live-key testing is for the buyer.
- Legal texts (privacy, terms) are templates and need review by a lawyer in the buyer's jurisdiction — the app handles photos of children.
- Third-party API costs and terms (Anthropic, fal.ai) apply to the buyer.

**What you receive:** GitHub repository transfer, handover guide, deployment guide, test harness, and 14 days of email Q&A for setup questions.

## Short pitch (for DMs / email)
See BUYER_OVERVIEW_EN.md, section "Short pitch".
