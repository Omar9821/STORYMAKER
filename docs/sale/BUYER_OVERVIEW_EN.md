# Buyer overview — Personalized Children's Storybook Platform

## Short pitch
A finished, deployable platform that creates personalized, illustrated children's storybooks and coloring books from a child's photo, in Arabic, French and English, with print-ready PDF output and an admin dashboard. Pre-revenue; sold with full source code, documentation and deploy configs. Rebuilding this would take weeks of engineering plus iteration on prompts, PDF layout and face consistency.

## Architecture
- Frontend: React (CRA/craco), Tailwind, i18n (ar/fr/en). Static hosting (Netlify).
- Backend: FastAPI + MongoDB (Motor). Persistent job queue in Mongo, one active job per order, stale-job recovery.
- AI: Claude for story JSON; fal.ai PuLID / multi-reference for illustrations. Direct API keys, no vendor lock-in.
- PDFs: ReportLab with Arabic reshaping/bidi; print specs A5 + 3 mm bleed, 300 dpi.
- Storage: S3-compatible (Cloudflare R2) or local; signed expiring URLs.
- Payments: Chargily Pay (Algeria) + cash on delivery. Mock mode is explicit (PAYMENT_MOCK=true).
- Security work done: required secrets (no defaults), brute-force lockout, input validation, rate limits, no wildcard CORS with credentials, atomic coupons, public order view without personal data.

## Running costs (estimate — verify current prices)
| Item | Cost |
|---|---|
| Render backend (Starter) | ~$7/month |
| Netlify, MongoDB Atlas M0, Cloudflare R2 (small scale) | free tiers |
| AI per book | depends on page count and image model; the admin dashboard has a cost ledger that records actual spend per order |

## Known limitations (be aware before buying)
1. No customers or revenue history.
2. Live payment and live print-shop integration are not tested; print specs are generic.
3. Legal pages are templates, not legal advice.
4. Illustration quality depends on fal.ai models and the quality of the uploaded photo.
5. Single-server job worker (fine for early volume; scale by moving to a separate worker).
6. Frontend is not covered by automated browser tests.

## Growth ideas
Print-on-demand integration, video/animated stories, B2B for schools and nurseries, subscriptions, gift cards, more languages and themes.

## FAQ
**Who owns the code?** The seller; ownership transfers on payment via the marketplace escrow.
**Is it AI-generated?** Built with AI assistance, then reviewed and tested. Disclosed in the listing.
**Can I rename and rebrand?** Yes; brand strings are in i18n.js and public/index.html.
**Does it need Emergent or any proprietary platform?** No. Emergent-specific dependencies and tracking scripts were removed; it runs on plain Render/Netlify.
**Support after sale?** 14 days of email Q&A on setup.
