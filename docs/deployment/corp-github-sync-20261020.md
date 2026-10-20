# CORP / GitHub main synchronization — 2026-10-20

Reference: functional CORP `37a8e4f`; GitHub base `a1b4de7`. This synchronization preserves the deployed application source and publishes the previously local corrections as one commit. It does not import database configuration or runtime data.

## Previously unpublished corrections

- Oracle cloning: preserve device identities within the existing 40-character limit, including suffixes; preserve factory/role and omit browser identity/history on clones.
- Factory Perimeter migration: create the terminal-role check constraint so upgrade and downgrade agree.
- Atomic perimeter cascade: flush automatic cell EXIT before its perimeter FK; use original ENTER device/structure/context snapshots; shared timestamp/correlation and transaction retained.
- Scan protection: BOTH cooldown, dedicated exit exception, completed EXIT duplicate handling and unavailable external badge source rejection; regression for same-factory entry enforcement and concurrent scans.
- Perimeter-only terminals: New/Edit flag removes cell actions/context/structure/policies, valid gate identity, compatible cloning; validate cell conversion and reject direct cell events from gates.
- Action visibility safeguards: hidden active EXIT remains available internally; terminal active-entry/exit validation respects roles. Existing action visibility migration and selector retained.
- Perimeter administration: uniform styles, persisted factory query/localStorage, stale-response protection, exclusive error/success notices, unavailable saved EXIT feedback, explicit saved factory/role and refreshed assignments.
- Terminal feedback: translated perimeter results and duplicate feedback; preserve RFID/BOTH/KEYPAD capture.
- Unified monitoring: local-only perimeter event logs/details/clocks without Oracle preview, main-entry badge register, independent cell and enabled-factory states with SQL filters/count/pagination.
- Deployment: existing CORP Compose override and offline Dockerfiles; no dependency bundles, secrets or images committed.
- Tests and operational documentation, including pending deployment records and current/historical notes.

The sixteen visual keys and all twenty-three PNGs already present in GitHub remain byte-identical. Spanish reason labels, BSS supplier codes, action activation and terminal assignments are database configuration; they remain in CORP and are not exported to GitHub.

## Validation

Backend: 79 passed, 1 optional external database check skipped; includes isolated PostgreSQL migration/concurrency checks. Frontend: 40 passed; TypeScript/Vite build passed. Source hash audit: all 46 API modules match the running image. Worker runtime modules match; its older image differs only in unused monitoring router/schema modules. Live web JS/CSS and 23 PNGs are checked against the synchronized build. No production scans or Oracle transmissions.

## Files affected relative to GitHub main

- `.gitignore`
- `CURRENT_STATE.md`
- `MEMORY.md`
- `backend/Dockerfile.corp-offline`
- `backend/alembic/versions/0010_factory_perimeter.py`
- `backend/app/models/terminal.py`
- `backend/app/routers/admin.py`
- `backend/app/routers/monitoring.py`
- `backend/app/routers/perimeter.py`
- `backend/app/routers/terminal.py`
- `backend/app/schemas/admin.py`
- `backend/app/schemas/monitoring.py`
- `backend/app/services/configuration_service.py`
- `backend/app/services/event_service.py`
- `backend/app/services/perimeter_service.py`
- `backend/app/services/terminal_cloning_service.py`
- `backend/tests/test_action_visibility.py`
- `backend/tests/test_exit_policy_postgres.py`
- `backend/tests/test_perimeter.py`
- `backend/tests/test_perimeter_monitoring.py`
- `backend/tests/test_perimeter_postgres.py`
- `backend/tests/test_perimeter_terminal.py`
- `docker-compose.perimeter-corp.yml`
- `docs/deployment/action-visibility-corp-20261020.md`
- `docs/deployment/corp-github-sync-20261020.md`
- `docs/deployment/factory-perimeter-corp-20261020.md`
- `docs/deployment/perimeter-only-terminal-20261020.md`
- `docs/deployment/perimeter_fingerprint.py`
- `docs/deployment/perimeter_http_validation.py`
- `docs/deployment/visibility_http_validation.py`
- `docs/factory-perimeter.md`
- `frontend/Dockerfile.corp-offline`
- `frontend/nginx.conf`
- `frontend/src/admin.css`
- `frontend/src/components/EventInspector.tsx`
- `frontend/src/components/MonitoringPanel.tsx`
- `frontend/src/components/admin/PerimeterPanel.tsx`
- `frontend/src/components/admin/TerminalEditor.tsx`
- `frontend/src/components/admin/TerminalList.tsx`
- `frontend/src/components/monitoringTypes.tsx`
- `frontend/src/i18n.ts`
- `frontend/src/pages/AdminPage.tsx`
- `frontend/src/pages/TerminalPage.tsx`
- `frontend/tests/factory-card-state.test.tsx`
- `frontend/tests/perimeter-log.test.tsx`
- `frontend/tests/perimeter-terminal.test.tsx`
- `frontend/tests/perimeter.test.tsx`
- `frontend/tests/rfid.test.tsx`
