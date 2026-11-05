# CORP frontend release

The only supported frontend production release is `scripts/deploy-frontend.sh` from a clean checkout whose `HEAD` equals the latest `origin/main`. It discovers the Compose files attached to the running CORP web container, appends `docker-compose.frontend-release.yml` to override only the web build context and image, then builds and recreates only `web`.

`frontend/Dockerfile` uses `npm ci`, runs frontend tests and the Vite production build, and fails unless the result contains both Hutchinson logos, the RFID illustration, every action illustration referenced by the catalogue, and production HTML. The image embeds the exact source SHA as its OCI revision label and is tagged with that full SHA. The script refuses dirty or outdated source trees and refuses to deploy while the retired incomplete static package exists.
