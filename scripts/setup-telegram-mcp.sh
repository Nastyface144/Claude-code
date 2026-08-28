#!/usr/bin/env bash
# Скачивает и ставит Telegram MCP-сервер (chigwell/telegram-mcp) в vendor/telegram-mcp.
# Каталог vendor/ в .gitignore — код сервера не попадает в этот репозиторий.
set -euo pipefail

REPO_URL="https://github.com/chigwell/telegram-mcp.git"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${TELEGRAM_MCP_DIR:-$ROOT/vendor/telegram-mcp}"

if ! command -v uv >/dev/null 2>&1; then
  echo "Нужен uv: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

if [ -d "$DEST/.git" ]; then
  echo "==> Обновляю $DEST"
  git -C "$DEST" pull --ff-only
else
  echo "==> Клонирую $REPO_URL в $DEST"
  mkdir -p "$(dirname "$DEST")"
  git clone "$REPO_URL" "$DEST"
fi

echo "==> Ставлю зависимости (uv sync)"
(cd "$DEST" && uv sync)

if [ ! -f "$DEST/.env" ]; then
  cp "$DEST/.env.example" "$DEST/.env"
  echo "==> Создал $DEST/.env — впиши TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_SESSION_STRING"
fi

cat <<MSG

Готово. Дальше:
  1) https://my.telegram.org/apps -> получи API_ID и API_HASH
  2) cd "$DEST" && uv run session_string_generator.py --qr
  3) впиши значения в $DEST/.env
  4) проверь запуск:  cd "$DEST" && uv run main.py
Подробности: docs/telegram-mcp.md
MSG
