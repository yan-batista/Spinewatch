#!/usr/bin/env bash
# Run on the VM (piped over SSH by .github/workflows/deploy.yml) to pull the
# freshly-pushed images and restart the API container. The crawl image needs
# no restart -- cron just runs whatever `spinewatch:latest` points to next.
set -euo pipefail

OWNER=yan-batista

docker pull "ghcr.io/$OWNER/spinewatch:crawl"
docker tag "ghcr.io/$OWNER/spinewatch:crawl" spinewatch:latest

docker pull "ghcr.io/$OWNER/spinewatch:api"

# Keep the image the running container was built from, so a failed rollout can
# be put back exactly as it was.
docker tag spinewatch-api:latest spinewatch-api:previous 2>/dev/null || true
docker tag "ghcr.io/$OWNER/spinewatch:api" spinewatch-api:latest

start_api() {
  docker rm -f spinewatch-api >/dev/null 2>&1 || true
  docker run -d --restart unless-stopped --name spinewatch-api \
    -v /srv/spinewatch/data:/data:z \
    --env-file /srv/spinewatch/api.env \
    -p 127.0.0.1:8000:8000 \
    "$1"
}

start_api spinewatch-api:latest

# The container can start and still be broken (bad env file, unreadable volume,
# a bug in the new image). Prove it actually answers before walking away.
for _ in $(seq 30); do
  if curl -fsS -o /dev/null http://127.0.0.1:8000/books; then
    docker image prune -f
    exit 0
  fi
  sleep 1
done

echo "new API image failed its health check -- rolling back" >&2
docker logs --tail 50 spinewatch-api >&2 || true
if docker image inspect spinewatch-api:previous >/dev/null 2>&1; then
  docker tag spinewatch-api:previous spinewatch-api:latest
  start_api spinewatch-api:latest
fi
exit 1
