# Радар фриланс-заказов в Telegram

Бот следит за биржами фриланса и присылает в Telegram только те заказы, которые
подходят под твои темы:

- **Telegram-боты** (aiogram, pyrogram, telebot, чат-боты, автоматизация);
- **Telegram Mini Apps / TWA** (мини-приложения внутри Telegram);
- **Лендинги** (одностраничные сайты, сайты-визитки, вёрстка).

Всё управление — прямо в чате с ботом: пороги, ключевые слова, источники.

---

## Как это работает

```
RSS-ленты бирж  ──►  парсер  ──►  фильтр по темам  ──►  дедупликация  ──►  Telegram
   (fl.ru, Хабр      (Order)      (баллы + теги)        (SQLite)         (только новое)
    Weblancer …)
```

1. Раз в `POLL_INTERVAL` секунд бот забирает свежие объявления со всех включённых лент.
2. Каждый заказ получает **балл релевантности**: правила из `freelance_bot/keywords.py`
   складываются, штрафы (другой мессенджер, WordPress, вакансия в штат) вычитаются,
   стоп-слова (накрутка, казино, «продам бота») выкидывают заказ совсем.
3. Заказы с баллом ≥ порога уходят в чат. Дубли не приходят повторно никогда:
   у каждого объявления стабильный `uid`, а факт отправки пишется в базу.

Пример оценки:

```
$ python -m freelance_bot filter "Нужен телеграм бот с mini app и лендингом"
Балл: 24
Теги: telegram-бот, mini app, лендинг, бот, telegram
Почему: telegram-бот +6, mini app +6, лендинг +6, бот +3, telegram +3
```

---

## Быстрый старт

```bash
git clone <этот репозиторий>
cd claude-code

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# впиши BOT_TOKEN, полученный у @BotFather

python -m freelance_bot run
```

Дальше в Telegram: открой своего бота и нажми **/start**.

### Docker

```bash
cp .env.example .env      # впиши BOT_TOKEN
docker compose up -d --build
docker compose logs -f
```

### systemd

Готовый юнит — в `deploy/freelance-bot.service` (положить проект в `/opt/freelance-bot`,
создать там venv, затем `systemctl enable --now freelance-bot`).

---

## Команды бота

| Команда | Что делает |
|---|---|
| `/start` | включить рассылку |
| `/stop` | выключить рассылку |
| `/check` | опросить биржи прямо сейчас и показать отчёт |
| `/last [N]` | последние найденные подходящие заказы (по умолчанию 5) |
| `/search <текст>` | поиск по уже собранным заказам |
| `/status` | состояние: источники, счётчики, твои настройки |
| `/score <N>` | минимальный балл релевантности (обычно 4–8) |
| `/keywords` | какие правила сейчас работают |
| `/add <слово> [вес]` | своё ключевое слово, `*` = любое окончание: `/add уведомлени* 6` |
| `/ban <слово>` | слово-исключение: такие заказы не приходят |
| `/del <слово>` | убрать своё слово |
| `/sources` | список лент и их состояние (✅ / ⚠️ с текстом ошибки / ⏸) |
| `/addsource <имя> <url>` | добавить RSS-ленту биржи |
| `/delsource <имя>` | удалить ленту |
| `/togglesource <имя>` | временно выключить/включить ленту |

Любой текст без команды бот воспринимает как быстрый поиск по найденным заказам.

Настройки `/score`, `/add`, `/ban` — **личные для каждого чата**, поэтому одного бота
можно спокойно использовать вдвоём или в группе.

---

## Командная строка

```bash
python -m freelance_bot run                  # запустить бота (то же, что без аргументов)
python -m freelance_bot dryrun               # опросить биржи и вывести находки в консоль
python -m freelance_bot filter "текст"       # посмотреть, как оценивается конкретный текст
python -m freelance_bot -v run               # подробные логи
```

`dryrun` и `filter` работают без токена Telegram — удобно подбирать ключевые слова.

---

## Настройка (.env)

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `BOT_TOKEN` | — | токен от [@BotFather](https://t.me/BotFather), обязателен |
| `DB_PATH` | `data/freelance.db` | файл базы SQLite |
| `POLL_INTERVAL` | `600` | период опроса бирж, секунд (минимум 60) |
| `MIN_SCORE` | `5` | порог релевантности по умолчанию |
| `MAX_PER_CYCLE` | `10` | сколько заказов максимум слать в один чат за цикл |
| `REQUEST_TIMEOUT` | `20` | таймаут HTTP-запроса к бирже, секунд |
| `ADMIN_IDS` | — | id админов через запятую (задел на будущее) |

---

## Источники

По умолчанию заведены RSS-ленты четырёх бирж:

| Имя | Биржа | Лента |
|---|---|---|
| `fl` | FL.ru | `https://www.fl.ru/rss/all.xml` |
| `habr` | Хабр Фриланс | `https://freelance.habr.com/tasks.rss` |
| `weblancer` | Weblancer | `https://www.weblancer.net/rss/projects/` |
| `freelanceru` | Freelance.ru | `https://freelance.ru/rss/projects` |

Биржи иногда меняют адреса лент и закрывают их от «неизвестных» клиентов. Поэтому
состояние каждой ленты видно в `/sources`: если там ⚠️ с ошибкой (403, 404, timeout) —
поменяй адрес на актуальный:

```
/delsource habr
/addsource habr https://freelance.habr.com/tasks.rss?q=telegram Хабр Фриланс
```

Так же добавляются любые другие ленты: тематический поиск на бирже, RSS Telegram-канала
с заказами через сторонний rss-мост, персональная лента с фильтрами биржи.

### Свой тип источника (не RSS)

Если у биржи нет RSS, добавь класс-наследник `Source`:

```python
# freelance_bot/sources/my_board.py
from .base import Source
from ..models import Order

class MyBoardSource(Source):
    async def fetch(self, session) -> list[Order]:
        async with session.get(self.config.url) as response:
            payload = await response.json()
        return [
            Order(
                source=self.name,
                external_id=str(item["id"]),
                title=item["name"],
                url=item["link"],
                description=item["text"],
            )
            for item in payload["items"]
        ]
```

и зарегистрируй его в `freelance_bot/sources/registry.py`:

```python
KINDS = {"rss": RssSource, "myboard": MyBoardSource}
```

Ошибка одного источника никогда не роняет опрос: она попадает в `/sources` и в отчёт `/check`.

---

## Как настроить фильтр под себя

Базовый профиль лежит в `freelance_bot/keywords.py` (`INCLUDE_RULES`, `PENALTY_RULES`,
`STOP_RULES`) — это регулярки по нормализованному тексту, поэтому «Телеграм-бот»,
«телеграм бот» и «TELEGRAM_BOT» распознаются одинаково.

Обычно править файл не нужно, хватает команд:

```
/score 6                 # строже: меньше случайных заказов
/add telegram stars 6    # своя тема
/add уведомлени*         # «*» — любое окончание, вес по умолчанию 5
/ban wordpress           # мусор, который надоел
/keywords                # посмотреть, что сейчас включено
```

---

## Разработка

```bash
pip install -r requirements-dev.txt
python -m pytest -q          # 45 тестов: фильтр, парсер RSS, база, сервис, команды бота
```

Структура:

```
freelance_bot/
├── app.py          — сборка Bot + Dispatcher + фоновой опрос
├── cli.py          — run / dryrun / filter
├── bot.py          — команды Telegram
├── service.py      — цикл опроса, фильтрация, рассылка, дедупликация
├── matcher.py      — оценка релевантности
├── keywords.py     — профиль тем: боты, mini apps, лендинги
├── models.py       — Order (единый формат заказа)
├── storage.py      — SQLite: подписчики, заказы, доставки, слова, источники
├── formatting.py   — тексты сообщений
└── sources/        — источники: base / rss / registry
tests/              — pytest
```

Заказы старше 30 дней автоматически удаляются из базы после каждого цикла.
