# Shorts Factory

Пайплайн для автоматической сборки YouTube Shorts из историй с Reddit:
**Reddit → текст → озвучка → субтитры → вертикальное видео → YouTube**.

Проект собран из независимых модулей: каждый читает и пишет очередь историй
(`data/queue.json`), поэтому любой шаг можно запускать, отлаживать и заменять
отдельно, а оркестратор просто связывает их по статусам.

**Статус:** реализован модуль 1 (Reddit Scraper) вместе с общей инфраструктурой
(конфиг, очередь, логирование, ретраи, CLI, тесты). Остальные модули — в
дорожной карте ниже.

---

## Структура проекта

```
.
├── .env.example                     # шаблон конфигурации (ключи API и параметры)
├── requirements.txt
├── pytest.ini
├── shorts_factory/
│   ├── config.py                    # загрузка/валидация настроек из .env
│   ├── logging_setup.py             # единое логирование (stderr + файл)
│   ├── models.py                    # Story, StoryStatus — модель единицы работы
│   ├── storage.py                   # StoryQueue: очередь на JSON с атомарной записью
│   ├── cli.py                       # точка входа: scrape / list / show / stats / remove
│   ├── utils/
│   │   ├── retry.py                 # ретраи с экспоненциальной задержкой, Retry-After
│   │   └── text.py                  # очистка Reddit-разметки, подсчёт слов
│   └── pipeline/
│       ├── reddit_scraper.py        # ✅ модуль 1
│       ├── text_processor.py        # ⬜ модуль 2
│       ├── tts.py                   # ⬜ модуль 3
│       ├── subtitles.py             # ⬜ модуль 4
│       ├── background.py            # ⬜ модуль 5
│       ├── assembler.py             # ⬜ модуль 6
│       ├── uploader.py              # ⬜ модуль 7
│       └── orchestrator.py          # ⬜ модуль 8
├── assets/backgrounds/              # библиотека фоновых видео (не в git)
├── data/queue.json                  # очередь историй (не в git)
├── work/                            # промежуточные артефакты: аудио, .ass, кропы
├── output/                          # готовые mp4
└── tests/                           # тесты без сети и ключей API
```

## Как это работает

Единица работы — `Story`. Скрапер создаёт её в статусе `new`, каждый следующий
модуль дополняет её артефактами и переводит в следующий статус:

```
new → text_ready → audio_ready → subs_ready → video_ready
    → pending_review → approved → uploaded
                    ↘ rejected / failed
```

Так оркестратор становится тривиальным: «взять первую историю в статусе X,
выполнить шаг, перевести в статус Y», а любой упавший шаг можно перезапустить,
не трогая остальные.

## Быстрый старт

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # заполнить REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET
```

Ключи Reddit: https://www.reddit.com/prefs/apps → **create app** → тип **script**.
`client_id` — строка под названием приложения, `client_secret` — поле *secret*.
`REDDIT_USER_AGENT` обязателен и должен быть осмысленным
(`python:shorts-factory:0.1.0 (by /u/username)`) — Reddit банит безликие агенты.

```bash
# посмотреть, что отберут фильтры, ничего не записывая
python -m shorts_factory.cli scrape --dry-run

# собрать истории в очередь
python -m shorts_factory.cli scrape --time-filter week --max-stories 5

# работа с очередью
python -m shorts_factory.cli list --status new
python -m shorts_factory.cli show <story_id>
python -m shorts_factory.cli stats
python -m shorts_factory.cli remove <story_id>
```

Тесты (сеть и ключи не нужны — Reddit подменяется фейками):

```bash
python -m pytest
```

## Модуль 1: Reddit Scraper (реализован)

`shorts_factory/pipeline/reddit_scraper.py`

Что делает:

* берёт `top(time_filter)` из каждого сабреддита списка `SUBREDDITS`;
* фильтрует посты: длина в словах (`MIN_WORDS`..`MAX_WORDS`), рейтинг
  (`MIN_SCORE`), доля апвоутов (`MIN_UPVOTE_RATIO`), NSFW, закреплённые,
  удалённые/пустые тела;
* длину считает по **очищенному** тексту, чтобы markdown и ссылки не
  раздували счётчик;
* складывает подходящие истории в `StoryQueue` со статусом `new`.

**Два источника текста.** Это ключевой нюанс: у постов r/AskReddit тело пустое —
история живёт в комментариях. Источник задаётся в `SUBREDDITS` через двоеточие:

```
SUBREDDITS=tifu:selftext,confession:selftext,AskReddit:comments
```

* `selftext` — текст берётся из тела поста;
* `comments` — берутся топ-комментарии (пропуская закреплённые, удалённые и
  слишком короткие) и добираются по одному, пока суммарная длина не попадёт в
  окно `MIN_WORDS..MAX_WORDS`. Каждый комментарий сохраняется отдельным
  элементом `story.segments` — дальше их удобно озвучивать разными голосами
  или разделять паузами.

**Дедупликация.** Очередь хранит `seen` — id всех рассмотренных постов, включая
отклонённые. Повторный запуск (например, ежечасный cron) не потратит квоту на
уже виденное; записи старше `seen_ttl_days` (60 дней) вычищаются.

**Ошибки и rate limits:**

* PRAW сам соблюдает лимиты Reddit по заголовкам `X-Ratelimit-*`
  (`ratelimit_seconds=600`);
* поверх — ретраи с экспоненциальной задержкой (2s → 4s → 8s → 16s + джиттер)
  на `TooManyRequests`, `ServerError`, `RequestException` и обрывы соединения,
  с уважением заголовка `Retry-After`;
* неповторяемые ошибки (403/404, неверные ключи) поднимаются сразу — ждать
  бессмысленно;
* сбой одного сабреддита не роняет запуск: он попадает в отчёт `ScrapeReport`,
  остальные обрабатываются;
* между сабреддитами — пауза `REQUEST_DELAY_SECONDS`;
* нехватка ключей — это ошибка запуска (выход с кодом 2), а не сбой шага.

Отчёт `ScrapeReport` показывает, сколько постов просмотрено, принято и по каким
причинам отклонено (`too_short`, `low_score`, `already_seen`, …) — по нему
удобно калибровать фильтры, не гадая.

Пример использования из кода:

```python
from shorts_factory.config import Settings
from shorts_factory.pipeline import RedditScraper

settings = Settings.load()
report = RedditScraper(settings).run(time_filter="day", max_stories=5)
print(report.summary())
```

## Дорожная карта

| # | Модуль | Что делает | Ключевые решения |
|---|--------|-----------|------------------|
| 2 | `text_processor` | Чистит текст, сокращает под `TARGET_DURATION_SECONDS` (~150 слов ≈ 60 c при 150 wpm), генерирует цепляющую первую фразу и заголовок | Prompt к LLM + обязательный контроль длины; результат в `story.text`, статус `text_ready` |
| 3 | `tts` | Озвучка через ElevenLabs или бесплатный edge-tts | Общий интерфейс `synthesize(text, out_path) -> duration`; кэш по `story.id`; ретраи на 429 |
| 4 | `subtitles` | Whisper по готовому аудио → пословные таймкоды → `.ass` в стиле караоке | Транскрибировать **сгенерированное аудио**, а не исходный текст — так таймкоды точные даже при оговорках TTS |
| 5 | `background` | Случайный отрезок нужной длины из `assets/backgrounds`, кроп в 9:16 | `ffprobe` для длительности, `crop`/`scale` в 1080×1920, не повторять один и тот же отрезок подряд |
| 6 | `assembler` | FFmpeg: фон + аудио + субтитры → mp4 | Один вызов ffmpeg с `-vf "crop=...,subtitles=story.ass"`, `-c:v libx264 -preset veryfast`, `-shortest` |
| 7 | `uploader` | YouTube Data API v3: загрузка, заголовок, описание, теги, `#Shorts` | OAuth-токен в `token.json`; квота 10 000 единиц/сутки ≈ 6 загрузок — планировать расписание |
| 8 | `orchestrator` | Прогон очереди по статусам, логи, ручная проверка перед публикацией | `REQUIRE_MANUAL_REVIEW=true`: видео уходит в `pending_review`, публикуется только после `approved` |

## Прежде чем публиковать

Пайплайн умышленно останавливается на ручной проверке — это не бюрократия, а
условие того, чтобы канал прожил дольше месяца:

* **Политика YouTube про Inauthentic Content.** Массово залитые однотипные
  ролики без добавленной ценности демонетизируются. Реальную защиту дают
  отбор историй, монтаж и оформление, а не объём.
* **Права на контент.** Тексты Reddit принадлежат их авторам; фоновый геймплей —
  правообладателям игр. Указывайте источник, не выдавайте чужую историю за свою
  и не используйте фон, на который нет прав.
* **Модерация.** Автоматика не отличит грубый или травмирующий сюжет от
  безобидного, а деанонимизирующие детали (имена, места работы) — от вымысла.
  `ALLOW_NSFW=false` — минимум, а не замена человеку.
* **Reddit API.** Соблюдайте [условия использования](https://www.redditinc.com/policies/data-api-terms):
  осмысленный User-Agent, отсутствие агрессивного поллинга и коммерческого
  использования данных сверх разрешённого.

Начинайте с `YOUTUBE_PRIVACY_STATUS=private` и переключайтесь на публикацию,
только просмотрев готовые ролики.
