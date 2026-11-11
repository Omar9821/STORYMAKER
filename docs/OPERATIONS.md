# Operations guide

## Daily workflow (admin)
1. New order arrives as **awaiting_payment**. Call the customer, agree the **shipping fee**, then press
   **Confirm & start generation** (phone-confirmation box in the order drawer). Online (Chargily) orders start by themselves.
2. Wait for **review** (about 2-3 minutes). Check every page: text, faces, clothes, the family members present, coloring pages.
   Use the per-page regenerate button, or *Regenerate text* (re-draws the pictures too by default so text and pictures stay in sync).
3. **Approve**. The customer can now see the book and download the PDF on the tracking page (before approval they only see the status).
4. Press **Build print files** → download *interior* (A5 + 3 mm bleed, 300 dpi, multiple of 4 pages) and *cover spread*, send them to the printer.
   For Arabic books the binding edge is on the **right**.
5. Mark printing → shipped → delivered. Reference photos are deleted automatically on shipping/delivery.

## Background jobs
Every generation/regeneration is a persisted job (`jobs` collection). One active job per order (a second click returns 409).
If the server restarts mid-job it is re-queued once; a second interruption marks the order *failed* and sends an alert.

## Monitoring
* `GET /api/health` → 200 when MongoDB and storage work, 503 otherwise. Point UptimeRobot/BetterStack at it.
* Alerts: set `ALERT_TELEGRAM_BOT_TOKEN`+`ALERT_TELEGRAM_CHAT_ID` (or `ALERT_WEBHOOK_URL`). You get a message when a generation fails.

## Backups
`mongodump --uri "$MONGO_URL" --db "$DB_NAME" --gzip --archive=hikayati-$(date +%F).gz` once a day (cron), copy it off the server,
and test a restore. Files live in the storage backend; with `STORAGE_BACKEND=s3` enable bucket versioning.

## Privacy
Reference photos are really deleted (shipped/delivered, cancelled, refunded, unpaid > `RETENTION_UNPAID_DAYS`, or on demand).
`/api/admin/privacy-logs` records how many files were deleted or failed. If the Emergent storage service rejects DELETE, the order
is flagged `reference_files_failed` and the sweeper retries every 6 hours — check the log after the first real order.

## What has NOT been verified against the real services
Written and tested with fake providers: multi-person illustrations (`MULTI_REF_ENDPOINT`), the optional upscaler,
direct fal / Anthropic modes (`FAL_KEY`, `ANTHROPIC_API_KEY`), S3 backend, Emergent object deletion, and the Chargily amount check.
Run one real order of each kind after deploying and look at the illustrations before announcing.
