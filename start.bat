@echo off
rem Запуск радара заказов на Windows. Первый раз спросит токен от @BotFather.
cd /d "%~dp0"

if not exist .env (
  echo Нужен токен бота от @BotFather ^(вида 123456:AA...^)
  set /p token="Вставь токен и нажми Enter: "
  if "%token%"=="" (echo Токен не введён — выходим. & pause & exit /b 1)
  (
    echo BOT_TOKEN=%token%
    echo DB_PATH=data/freelance.db
    echo POLL_INTERVAL=600
    echo MIN_SCORE=5
  ) > .env
  echo Токен сохранён в .env
)

if not exist .venv (
  echo Готовлю окружение...
  python -m venv .venv
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\pip install --quiet -r requirements.txt
)

echo Бот запущен. Напиши ему /start в Telegram. Остановить — Ctrl+C.
.venv\Scripts\python -m freelance_bot run
pause
