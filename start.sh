#!/usr/bin/env bash
# Запуск радара заказов на своём компьютере или VPS.
# Первый раз спросит токен от @BotFather и сохранит его в .env.
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Нужен токен бота от @BotFather (вида 123456:AA...)"
  read -r -p "Вставь токен и нажми Enter: " token
  [ -n "$token" ] || { echo "Токен не введён — выходим."; exit 1; }
  printf 'BOT_TOKEN=%s\nDB_PATH=data/freelance.db\nPOLL_INTERVAL=600\nMIN_SCORE=5\n' "$token" > .env
  echo "Токен сохранён в .env (этот файл не попадёт в git)."
fi

if [ ! -d .venv ]; then
  echo "Готовлю окружение…"
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

echo "Бот запущен. Напиши ему /start в Telegram. Остановить — Ctrl+C."
exec .venv/bin/python -m freelance_bot run
