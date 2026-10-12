# Original PNG illustrations — validation and rollout

Source: Marcos's `frontend/public/BSS_TimeCollection_action_illustrations.zip`.
The archive contains seven 720 × 720 RGBA PNGs and a README. All seven local
assets are byte-identical to the archive entries; no artwork was generated,
resized or re-encoded. The original ZIP is retained locally and in the backup.

Admin Action/Sub-action previews and terminal cards now request `.png` instead
of `.svg`. The seven stable visual keys, optional empty selection, configuration
controls, light card backgrounds and `object-fit: contain` are preserved. The
existing Dockerfile already bundles this local directory. The unused seven SVG
placeholders are removed; the unrelated RFID illustration remains unchanged.

## Validation before production rollout

- Backend suite in the existing API container: **27 passed, 1 skipped**. The
  skipped check requires optional concurrency integration infrastructure. One
  existing Starlette/httpx deprecation warning remains.
- `docker compose build web`: TypeScript and Vite production build passed.
- Candidate production image served temporarily on port 18092, using the
  existing API and Docker network. Playwright checked 320×568, 390×844,
  768×1024, 1280×800 and 1920×1080; the first three used touch contexts.
- Every viewport loaded all seven PNGs in the Admin picker and terminal
  cards. Browser checks confirmed 720×720 natural dimensions, actual alpha
  transparency, `contain`, light backgrounds, usable touch targets and no
  horizontal document overflow. Touch selection and Factory exit navigation
  displayed the three second-level reason illustrations. No JavaScript errors.
- Admin reads used the real API. Terminal config/scan/exit responses were
  intercepted to exercise all seven scenes without generating production
  events or provisioning a browser. Existing backend tests cover configurable
  visuals and the real Action/Sub-action flow. This was browser touch emulation,
  not a test on physical RFID hardware.
- Visual review of the original picker: [screenshot](action-png-picker-validation.png).
- `git diff --check` passed. Existing local sidebar CSS and project notes are
  preserved outside the illustration commit.

## Backup and configuration correction

Backup: `/opt/backups/BSS_TimeCollection/20261012-original-png-illustrations/`.
It includes a verified custom-format PostgreSQL dump and contents list,
repository bundle, source/configuration archive including `.env` and the
original ZIP, previous running web image, environment checksum and row snapshots.

The requested correction was applied transactionally after backup:

```sql
UPDATE actions SET visual_key = 'factory'
WHERE code = 'FACTORY_EXIT' AND visual_key = 'end-work';
```

Exactly one row changed. Real Admin subsequently selected Factory exit's
`factory` preview. Row comparisons confirmed unchanged events, attempts,
terminals, terminal/action assignments and every other action field. Transient
pairing requests continue their normal expiry lifecycle. Baseline: 60 events,
0 attempts, 10 actions, 11 terminals and 65 terminal/action assignments.
No schema migration is needed; Alembic remains `0007_seed_action_visuals`.
`.env` checksum is unchanged and Oracle remains disabled.

## Production rollout

After publishing the validated frontend commit to `main`, deploy the already
built candidate with `docker compose up -d --no-deps web`. Check web/API health,
repeat the browser matrix against port 8092 and compare the served PNG bytes to
the source ZIP. Preserve the PostgreSQL volume and existing API/worker
containers; remove the temporary validation container after verification.
