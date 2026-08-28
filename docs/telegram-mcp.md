# Telegram MCP — установка и подключение

MCP-сервер для Telegram: даёт Claude (Claude Code, Claude Desktop, Cursor)
доступ к твоему **аккаунту** Telegram — читать чаты, искать сообщения,
отправлять сообщения и файлы, управлять группами и контактами.

- Репозиторий: <https://github.com/chigwell/telegram-mcp>
- Лицензия: Apache-2.0
- Проверено на коммите `52cca20` (23.08.2026), версия 2.0.1
- Под капотом Telethon (MTProto), Python 3.10+

> ⚠️ Это **не** бот из этого репозитория. Радар фриланс-заказов работает через
> bot API и `BOT_TOKEN` от @BotFather, а Telegram MCP заходит под твоим личным
> аккаунтом (по session string). Это разные вещи и разные учётные данные.

## Безопасность — прочитай до установки

- **Не ставь пакет `telegram-mcp` из PyPI** (`pip install telegram-mcp`,
  `uvx telegram-mcp`, `uvx --from telegram-mcp`). Имя на PyPI занято другим
  проектом; передав туда `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` /
  `TELEGRAM_SESSION_STRING`, ты отдашь доступ к аккаунту чужому коду.
  Ставить только из git-клона — как в скрипте ниже.
- Session string = полный доступ к аккаунту. Хранить только в `.env`
  (он в `.gitignore`), не коммитить, не пересылать.
- Если нужен доступ «только на чтение», поставь в `.env`
  `TELEGRAM_EXPOSED_TOOLS=read-only` — тогда инструменты записи (отправка
  сообщений, изменения в чатах) не регистрируются в MCP вообще.
  Промежуточный вариант: `TELEGRAM_EXPOSED_TOOLS=read-only+send_message`.
- Сессию можно отозвать в любой момент: Telegram → Настройки → Устройства.

## Установка

```bash
./scripts/setup-telegram-mcp.sh
```

Скрипт клонирует сервер в `vendor/telegram-mcp` (каталог в `.gitignore`),
ставит зависимости через `uv sync` и создаёт `.env` из примера.
Нужен [uv](https://docs.astral.sh/uv/getting-started/installation/).

Хочешь другой каталог — задай `TELEGRAM_MCP_DIR`:

```bash
TELEGRAM_MCP_DIR=~/mcp/telegram-mcp ./scripts/setup-telegram-mcp.sh
```

## Настройка

1. Получи `API_ID` и `API_HASH` на <https://my.telegram.org/apps>.
2. Сгенерируй session string (QR — удобнее всего, Telegram на телефоне под рукой):

   ```bash
   cd vendor/telegram-mcp
   uv run session_string_generator.py --qr   # или --phone для входа по коду из SMS
   ```

3. Впиши всё в `vendor/telegram-mcp/.env`:

   ```env
   TELEGRAM_API_ID=1234567
   TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef
   TELEGRAM_SESSION_STRING=<строка из генератора>
   # TELEGRAM_EXPOSED_TOOLS=read-only
   ```

4. Проверь, что сервер поднимается (запустится и будет ждать stdio — это норма,
   выход по Ctrl+C):

   ```bash
   uv run main.py
   ```

## Подключение к Claude Code

В корне проекта уже лежит `.mcp.json` — при запуске `claude` в этом каталоге
сервер подхватится автоматически (Claude Code спросит подтверждение при первом
запуске проектных MCP-серверов):

```json
{
  "mcpServers": {
    "telegram": {
      "command": "uv",
      "args": ["--directory", "${TELEGRAM_MCP_DIR:-./vendor/telegram-mcp}", "run", "main.py"]
    }
  }
}
```

Проверка: `/mcp` в Claude Code — сервер `telegram` должен быть `connected`.

Альтернатива — добавить глобально, без привязки к проекту:

```bash
claude mcp add telegram -- uv --directory ~/mcp/telegram-mcp run main.py
```

## Подключение к Claude Desktop / Cursor

В `claude_desktop_config.json` (или `mcp.json` у Cursor):

```json
{
  "mcpServers": {
    "telegram-mcp": {
      "command": "/полный/путь/к/uv",
      "args": ["--directory", "/полный/путь/к/vendor/telegram-mcp", "run", "main.py"]
    }
  }
}
```

Здесь нужны **абсолютные** пути: у десктопных клиентов другой рабочий каталог
и урезанный `PATH`.

## Обновление

```bash
./scripts/setup-telegram-mcp.sh   # git pull + uv sync
```

## Если не работает

- `Session is not authorized` — пересоздай session string
  (`uv run session_string_generator.py --qr`).
- `AuthKeyDuplicatedError` — одна и та же сессия используется с двух IP.
  Сгенерируй несколько сессий и перечисли их в `TELEGRAM_SESSION_STRINGS`.
- Сервер не виден в клиенте — проверь, что `uv` доступен по абсолютному пути,
  и посмотри логи MCP-клиента.
- Telegram недоступен из сети — есть поддержка прокси
  (`TELEGRAM_PROXY_TYPE=socks5` и соседние переменные в `.env.example`).
