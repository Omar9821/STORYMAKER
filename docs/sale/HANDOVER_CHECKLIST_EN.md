# Handover checklist (seller → buyer, after payment clears in escrow)

## Seller does
- [ ] Transfer GitHub repository (or add buyer as owner) and confirm no secrets exist in git history (`git log -p | grep -i secret`), rotate anything suspicious.
- [ ] Rotate and remove: admin password, JWT_SECRET, Chargily key, Anthropic/fal keys, R2 keys, Mongo credentials. Buyer creates their own.
- [ ] Transfer domain / hosting accounts if included in the sale (Netlify site, Render service) or delete the demo deployment.
- [ ] Export demo data only if agreed; delete all customer photos and orders from the demo database and bucket.
- [ ] Deliver: docs/DEPLOY_AR.md (and English deploy guide), BUYER_OVERVIEW_EN.md, docs/OPERATIONS.md, backend/.env.example.
- [ ] Walk the buyer through one full order on a call or by email.

## Buyer does
- [ ] Create own MongoDB Atlas, Cloudflare R2, Anthropic, fal.ai, Chargily accounts.
- [ ] Deploy with render.yaml + netlify.toml; set env vars from backend/.env.example.
- [ ] Check /api/health returns mongo ok and storage ok.
- [ ] Place a test order, review the PDF, then set live payment keys.
- [ ] Have a lawyer review privacy and terms.

## Marketplace rules to remember
- Use Flippa's escrow; do not move the transfer off-platform before payment is secured.
- Never share account passwords; use the platform's transfer flows.
