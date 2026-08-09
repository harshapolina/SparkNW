#!/usr/bin/env bash
# Production deploy on Hetzner — full stack including daily auto-scrape.
# Run on the server:  bash scripts/deploy-hetzner.sh
set -euo pipefail

cd /opt/instascope

echo "==> Pull latest"
git pull origin main

echo "==> Ensure daily-scrape env defaults"
grep -q '^CELERY_TIMEZONE=' .env || echo 'CELERY_TIMEZONE=Asia/Kolkata' >> .env
grep -q '^DAILY_SCRAPE_HOUR_IST=' .env || echo 'DAILY_SCRAPE_HOUR_IST=8' >> .env
grep -q '^DAILY_SCRAPE_MINUTE_IST=' .env || echo 'DAILY_SCRAPE_MINUTE_IST=0' >> .env
grep -q '^DAILY_SCRAPE_STAGGER_SECONDS=' .env || echo 'DAILY_SCRAPE_STAGGER_SECONDS=12' >> .env
grep -q '^REDIS_URL=' .env || echo 'REDIS_URL=redis://redis:6379/0' >> .env
grep -q '^LIVE_SCRAPE=' .env || echo 'LIVE_SCRAPE=1' >> .env

echo "==> Bring up redis + api + worker + beat + web (restart unless-stopped)"
docker compose --profile full up -d --build redis api worker beat web

echo "==> Status"
docker compose ps

echo ""
echo "Expected Up: redis, api, worker, beat, web"
echo "Daily scrape fires at 08:00 Asia/Kolkata via Celery Beat (laptop can be off)."
echo "Logs: docker compose logs -f beat worker"
