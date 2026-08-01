#!/usr/bin/env bash
# Run on the VM (piped over SSH by .github/workflows/deploy.yml) to pull the
# freshly-pushed images and restart the API container. The crawl image needs
# no restart -- cron just runs whatever `spinewatch:latest` points to next.
set -euo pipefail

OWNER=yan-batista

docker pull "ghcr.io/$OWNER/spinewatch:crawl"
docker tag "ghcr.io/$OWNER/spinewatch:crawl" spinewatch:latest

docker pull "ghcr.io/$OWNER/spinewatch:api"
docker tag "ghcr.io/$OWNER/spinewatch:api" spinewatch-api:latest

docker stop spinewatch-api
docker rm spinewatch-api
docker run -d --restart unless-stopped --name spinewatch-api \
  -v /srv/spinewatch/data:/data:z \
  --env-file /srv/spinewatch/api.env \
  -p 127.0.0.1:8000:8000 \
  spinewatch-api:latest

docker image prune -f
