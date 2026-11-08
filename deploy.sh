#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

command -v docker >/dev/null || { echo 'Ошибка: установите Docker.' >&2; exit 1; }
docker compose version >/dev/null || { echo 'Ошибка: установите Docker Compose.' >&2; exit 1; }
[[ -f .env ]] || { echo 'Ошибка: создайте .env на основе .env.example.' >&2; exit 1; }
set -a
source .env
set +a
[[ -n "${DOMAIN:-}" && -n "${SITE_URL:-}" ]] || { echo 'Ошибка: заполните DOMAIN и SITE_URL в .env.' >&2; exit 1; }
[[ "$SITE_URL" == "https://$DOMAIN" ]] || { echo 'Ошибка: SITE_URL должен быть https://DOMAIN.' >&2; exit 1; }
[[ "$DOMAIN" != example.ru ]] || { echo 'Ошибка: замените пример домена.' >&2; exit 1; }

docker compose config --quiet
docker compose up -d --build --wait
docker compose exec -T app python -c 'from app.main import init_db; init_db()'
docker compose exec -T app python -c 'import urllib.request; urllib.request.urlopen("http://localhost:8000/health", timeout=5)'
echo "Сайт запущен: $SITE_URL"
echo 'Проверьте DNS, HTTPS и доставку тестовой заявки после публикации.'
