# DormBuddy

Соседи, жильё и помощь после переезда — в одном студенческом сервисе.

**Учебный проект по практикуму Python · пилот: Москва · стадия: разработка MVP**

![Как устроен DormBuddy](assets/diagrams/product-overview.svg)

## Материалы проекта

Здесь ведём концепцию DormBuddy, требования к первой версии, технические решения и задачи. Основные документы — [концепция](docs/01-concept.md) и [MVP](docs/04-mvp.md); остальные разделы раскрывают отдельные части проекта.

| Материал | Что внутри |
| --- | --- |
| [Концепция и аудитория](docs/01-concept.md) | Для кого делаем сервис и какую задачу решаем |
| [Сценарии](docs/02-scenarios.md) | Соседи, жильё, общежитие и AI Buddy |
| [Алгоритм совместимости](docs/03-matching.md) | Ограничения, score, пропуски и объяснения |
| [Границы MVP](docs/04-mvp.md) | Что берём в первую версию и что откладываем |
| [Архитектура и данные](docs/05-architecture.md) | Модули, стек, сущности и требования к качеству |
| [Работа команды](docs/06-team-work.md) | Этапы, направления работы и чек-лист согласования |
| [Демо и проверки](docs/07-demo-and-quality.md) | Что должно работать к защите |
| [Решения и вопросы](docs/08-decisions.md) | Основа текущей концепции, предложения и открытые вопросы |
| [Backlog](docs/09-backlog.md) | Начальный список задач с условиями готовности |
| [Истории, Story Map и CJM](docs/10-product-design.md) | Черновики для дальнейшего проектирования |
| [Контекст системы C4](docs/11-system-context.md) | Пользователь, DormBuddy и внешний LLM |
| [Материалы преподавателю](docs/12-approval.md) | Сообщение, PDF и вопросы на согласование |
| [Вложения и изображения](docs/13-materials.md) | Актуальные файлы, ранние презентации и источники |

## Наша рабочая концепция

- Москва — тестовый город.
- «Соседи» и «Жильё» — независимые параллельные ленты.
- Подбор для общежития — один из центральных сценариев.
- Свайпы дополняются объяснимой оценкой совместимости.
- AI Buddy — контекстный помощник по переезду и быту.
- Если подходящих API жилья нет, используем тестовую базу; интеграции и монетизацию откладываем.

Овчинников одобрил тему DormBuddy после просмотра README. Мы начали разработку по рабочим [границам MVP](docs/04-mvp.md). Подробности фиксируем в [журнале решений](docs/08-decisions.md).

## Локальный запуск

Нужны Python 3.12+, [uv](https://docs.astral.sh/uv/) и Docker Compose. Из корня репозитория выполни:

```bash
cp -n .env.example .env
uv sync --locked
uv run python - <<'PY'
from pathlib import Path
from secrets import token_urlsafe

path = Path('.env')
contents = path.read_text()
placeholder = 'SESSION_SECRET=demo-placeholder-replace-with-a-random-secret'
if placeholder in contents.splitlines():
    path.write_text(contents.replace(placeholder, 'SESSION_SECRET=' + token_urlsafe(48), 1))
PY
docker compose up -d --wait
uv run alembic upgrade head
export DORMBUDDY_DEMO_PASSWORD='DormBuddy-demo-2026'
uv run python -m dormbuddy.seed
uv run uvicorn dormbuddy.main:app --host 127.0.0.1 --port 8000
```

Открой [http://127.0.0.1:8000](http://127.0.0.1:8000). Ключ сессии хранится в локальном `.env`, поэтому он доступен и из нового окна терминала. Для запуска за HTTPS установи `COOKIE_SECURE=true`. Если порт БД занят, согласуй `POSTGRES_PORT` и порт в `DATABASE_URL`.

### Демо

| Аккаунт | Что показать |
| --- | --- |
| `alisa@example.com` | Борис, объяснение score, первое «Нравится» |
| `boris@example.com` | Ответный лайк Алисе и одно общее сохранённое объявление |
| `nadya@example.com` | Олег в первом общежитии МИСИС, Соня после выбора второго |

Пароль всех демо-аккаунтов задаёт `DORMBUDDY_DEMO_PASSWORD` при первом seed. Повторный seed добавляет отсутствующие данные и сохраняет изменения существующих анкет, паролей и избранного. Наполняй только локальную демонстрационную БД. Полный порядок показа описан в [сценарии защиты](docs/07-demo-and-quality.md).

### Buddy

Используем API, совместимый с OpenAI Chat Completions. Настройки `BUDDY_BASE_URL`, `BUDDY_MODEL`, `BUDDY_API_KEY` и `BUDDY_TIMEOUT` (секунды) читаются из окружения или локального `.env`. По умолчанию URL указывает на OpenAI, модель — `gpt-4o-mini`. Без ключа Buddy сохраняет вопрос и показывает кнопку повтора. Остальные разделы работают независимо.

### Проверки

```bash
uv run alembic check
uv run pytest -q
```

Интеграционные тесты используют PostgreSQL из `DATABASE_URL`. Им нужен пользователь БД с правом создавать временные схемы. Тесты применяют миграцию в отдельной схеме и удаляют эту схему по завершении.

На отдельной, только что наполненной демобазе можно пройти браузерный сценарий. Он меняет демо-анкеты и лайки, сохраняет скриншоты в `/tmp/dormbuddy-screenshots` и проверяет состояние Buddy при пустом `BUDDY_API_KEY`.

```bash
uv run playwright install chromium
export DORMBUDDY_DEMO_PASSWORD='DormBuddy-demo-2026'
uv run python tests/browser_smoke.py
```

При необходимости задай `DORMBUDDY_BROWSER_URL`, `DORMBUDDY_CHROMIUM` (путь к установленному Chromium) или `DORMBUDDY_SCREENSHOTS`.

[Как вносить изменения](CONTRIBUTING.md) · [История изменений](CHANGELOG.md)
