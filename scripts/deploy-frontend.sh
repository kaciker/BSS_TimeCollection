#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
git fetch origin main --quiet
revision="$(git rev-parse HEAD)"
if [[ "$revision" != "$(git rev-parse origin/main)" ]]; then
  echo "Refusing deployment: checkout is not the latest GitHub main commit" >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing deployment: source checkout has uncommitted changes" >&2
  exit 1
fi
if [[ -e deploy-context-oracle-catalogue/static ]]; then
  echo "Refusing deployment: retired partial static package still exists" >&2
  exit 1
fi

export BSS_WEB_REVISION="$revision"
export BSS_FRONTEND_CONTEXT="$repo_root/frontend"
compose_project_dir="$(docker inspect bsstimecollection-web-1 --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}')"
compose_files="$(docker inspect bsstimecollection-web-1 --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' | tr ',' '\n')"
if [[ -z "$compose_files" || -z "$compose_project_dir" ]]; then
  echo "Cannot discover the running Compose stack files" >&2
  exit 1
fi
compose=(docker compose --project-directory "$compose_project_dir")
while IFS= read -r file; do
  [[ -n "$file" ]] && compose+=( -f "$file" )
done <<< "$compose_files"
compose+=( -f "$repo_root/docker-compose.frontend-release.yml" )
"${compose[@]}" build web
"${compose[@]}" up -d --no-deps --no-build web

web_url="${BSS_WEB_URL:-http://127.0.0.1:${WEB_PORT:-8080}}"
for route in /admin /terminal; do
  curl --fail --silent --show-error "$web_url$route" -o /dev/null
done
for asset in /img/logobig.png /img/hutchinson_logo.png /img/rfid-card.svg /action-visuals/factory.png; do
  content_type="$(curl --fail --silent --show-error -o /dev/null -w '%{content_type}' "$web_url$asset")"
  case "$asset:$content_type" in
    *.png:image/png|*.svg:image/svg+xml) ;;
    *) echo "Unexpected or missing frontend asset: $asset ($content_type)" >&2; exit 1 ;;
  esac
done
curl --fail --silent --show-error "$web_url/api/v1/health/ready" -o /dev/null
running_revision="$(docker inspect bsstimecollection-web-1 --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}')"
if [[ "$running_revision" != "$revision" ]]; then
  echo "Running web revision $running_revision does not match source $revision" >&2
  exit 1
fi

echo "Deployed and validated frontend source revision $revision"
