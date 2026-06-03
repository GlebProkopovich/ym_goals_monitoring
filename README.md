# ym_goals_monitoring

Python-проект для мониторинга целей Яндекс.Метрики с сохранением данных в PostgreSQL и уведомлениями в Telegram (опционально).

Проект реализует ETL-процесс и слой мониторинга:
- синхронизирует справочники (агентства → счётчики → цели);
- получает фактические достижения целей из API Яндекс.Метрики;
- сохраняет факты в БД;
- ищет аномалии в динамике достижений по категориям high/mid/low;
- выводит результат в консоль и при необходимости отправляет в Telegram.

## 1. Цель проекта

Автоматически находить потенциально «сломанные» цели Яндекс.Метрики: те, которые раньше стабильно срабатывали, но в последние дни перестали приносить достижения.

## 2. Точки входа

| Скрипт | Назначение | Когда запускать |
|--------|------------|-----------------|
| `python run_monitoring.py` | Факты → проверка → уведомления | Ежедневно (cron / Task Scheduler) |
| `python sync_metadata.py` | Счётчики и цели из API в БД | Периодически (например, раз в неделю) |

При ошибке любого этапа пишется лог и отправляется алерт (консоль + Telegram при `TELEGRAM_ENABLED=true`).

## 3. Структура проекта

```text
ym_goals_monitoring/
├─ run_monitoring.py      # ежедневный мониторинг
├─ sync_metadata.py       # синхронизация справочников
├─ requirements.txt
├─ db/
├─ extract/
├─ fetch/
├─ save/
├─ monitoring/
│  ├─ find_broken_goals.py
│  └─ periods.py           # период 13 дней для фактов
├─ telegram/
│  └─ alert_sender.py
└─ utils/
   ├─ http_retry.py        # retry + backoff для API
   ├─ pipeline_errors.py
   └─ logger.py
```

## 4. Ежедневный мониторинг (`run_monitoring.py`)

1. `extract_tracking_goals_info` — цели с `start_monitoring_date <= сегодня`.
2. `extract_counters_for_tracking_goals` — только счётчики этих целей.
3. `fetch_goals_fact` — факты за **13 календарных дней** (вчера−12 … вчера); API с retry; пропуск счётчиков, у которых все дни уже в БД; фильтр только по целям в мониторинге.
4. `save_goals_fact_to_db` — upsert в `ym_goals_fact`.
5. `find_broken_goals` — категории, статусы, уведомления.

## 5. Логика определения «сломанных» целей

Реализована в `monitoring/find_broken_goals.py`. Опорный день — **вчера** (сегодня не учитывается).

### Screening

Окно суммы — **10 календарных дней, включая вчера**.

Если сумма **≤ 10**, цель считается малошумной: в `ym_goals_statuses` ставится **`inactive`** без уведомлений, проверки поломки нет.

Если сумма **> 5**, дальше считается категория **high / mid / low** по эталонным окнам ниже и действует обычная логика `broken` / `active` и уведомления.

### Категории (эталон без вчера)

Применяются только если цель **не попала** в screening (`inactive` при сумме ≤ 10).

| Категория | Эталон (при вчера = 20 мая) | Условие | Окно проверки поломки |
|-----------|----------------------------|---------|------------------------|
| high | 10–19 мая | ≥ 100 | только вчера |
| mid | 9–18 мая | эталон mid ≥ 50 (и не попали в high — эталон high < 100) | вчера и позавчера |
| low | 8–17 мая | эталон mid < 50 | 3 дня до вчера включительно |

**Поломка:** сумма в окне проверки = 0.  
**Восстановление:** был статус `broken`, в окне ≥ 1.  
Повторные алерты по уже `broken` не отправляются.

### Статусы в `ym_goals_statuses`

- `active` — цель в норме
- `broken` — нет срабатываний в проверяемом окне
- `inactive` — мало трафика (сумма за 10 дней с вчера ≤ 10), без уведомлений

## 6. Синхронизация справочников (`sync_metadata.py`)

1. `extract_agencies_info` → `fetch_counters` → `save_counters_to_db`
2. Сравнение БД и API: счётчики, которые есть в БД, но не пришли из API, логируются как вероятно отозванный доступ (`sync/log_stale_counters.py`)
3. `extract_counters(api_counters=...)` — список для загрузки целей только из ответа API; устаревшие счётчики — лог в `sync/log_stale_counters.py`
4. `fetch_goals_info` → `save_goals_to_db`

## 7. База данных

### Таблицы

1. `agencies` — `id`, `name`
2. `ym_counters` — `id`, `name`, `agency_id`
3. `ym_goals` — `id`, `counter_id`, `type`, `name`, `start_monitoring_date`
4. `ym_goals_fact` — `date`, `goal_id`, `reaches`
5. `ym_goals_statuses` — `date`, `goal_id`, `status` (`active` / `broken` / `inactive`)

### DDL (минимальный)

```sql
CREATE TABLE IF NOT EXISTS agencies (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS ym_counters (
    id BIGINT NOT NULL,
    name TEXT NOT NULL,
    agency_id BIGINT NOT NULL REFERENCES agencies(id),
    PRIMARY KEY (id, agency_id)
);

CREATE TABLE IF NOT EXISTS ym_goals (
    id BIGINT PRIMARY KEY,
    counter_id BIGINT NOT NULL,
    type TEXT,
    name TEXT NOT NULL,
    start_monitoring_date DATE NULL
);

CREATE TABLE IF NOT EXISTS ym_goals_fact (
    date DATE NOT NULL,
    goal_id BIGINT NOT NULL REFERENCES ym_goals(id),
    reaches BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (date, goal_id)
);

CREATE TABLE IF NOT EXISTS ym_goals_statuses (
    date DATE NOT NULL,
    goal_id BIGINT NOT NULL REFERENCES ym_goals(id),
    status TEXT NOT NULL,
    PRIMARY KEY (goal_id),
    CONSTRAINT ym_goals_statuses_status_check
        CHECK (status IN ('active', 'broken', 'inactive'))
);

CREATE INDEX IF NOT EXISTS idx_ym_goals_fact_goal_date
    ON ym_goals_fact (goal_id, date);

CREATE INDEX IF NOT EXISTS idx_ym_goals_monitoring
    ON ym_goals (start_monitoring_date)
    WHERE start_monitoring_date IS NOT NULL;
```

Если таблица уже создана **без** `inactive` в CHECK (ошибка `ym_goals_statuses_status_check`), выполните в БД:

```sql
ALTER TABLE ym_goals_statuses DROP CONSTRAINT IF EXISTS ym_goals_statuses_status_check;

ALTER TABLE ym_goals_statuses
    ADD CONSTRAINT ym_goals_statuses_status_check
    CHECK (status IN ('active', 'broken', 'inactive'));
```

## 8. API Яндекс.Метрики

Все HTTP-запросы идут через `utils/http_retry.py` (до 4 попыток при ошибке, пауза 10 с между попытками).

### Суточный счётчик запросов

- Учёт только запросов к `api-metrika.yandex.net` (Telegram не считается).
- Каждая попытка HTTP, включая retry, увеличивает счётчик.
- Состояние: `logs/metrika_api_daily.json` (`date`, `count`). При смене календарной даты счётчик обнуляется автоматически.
- В конце `sync_metadata.py` и `run_monitoring.py` в лог пишется итог за сегодня.
- Программно: `from utils.metrika_api_counter import get_metrika_api_requests_today`

- Счётчики: `management/v1/counters`
- Цели: `management/v1/counter/{id}/goals`
- Факты: `stat/v1/data`, период 13 дней, `ym:s:anyGoalReaches`

## 9. Уведомления

`telegram/alert_sender.py`:

- **`TELEGRAM_TOKEN`**, **`TELEGRAM_CHAT_ID`** — для отправки в Telegram (по умолчанию включено, если заданы).
- **`TELEGRAM_ENABLED`** — `false` / `0` / `no`, чтобы отключить Telegram и оставить только консоль.
- Длинные сообщения режутся на части (лимит Telegram 4096 символов).
- **`notify_monitoring`** — результат проверки целей (консоль + опционально Telegram).
- **`send_pipeline_error_alert`** — сбой этапа пайплайна (всегда консоль и лог; Telegram при включённом флаге).

## 10. Переменные окружения (`.env`)

```dotenv
DB_HOST=...
DB_PORT=...
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_SCHEMA=...

TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
# TELEGRAM_ENABLED=false   # раскомментируйте, чтобы отключить Telegram

YM_API_TOKEN_<AGENCY_NAME>=...
```

Имя в `agencies.name` должно совпадать с суффиксом `YM_API_TOKEN_<AGENCY_NAME>`.

## 11. Установка и запуск

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Первичная настройка:

1. Создать таблицы (DDL выше).
2. Заполнить `agencies`, настроить `.env`.
3. `python sync_metadata.py` — загрузить счётчики и цели.
4. Проставить `start_monitoring_date` у нужных целей.
5. Ежедневно: `python run_monitoring.py`.

Проверка после запуска: `logs/project.log`, записи в `ym_goals_fact` и `ym_goals_statuses`, вывод в консоль / Telegram.

## 12. Карта по файлам

1. `run_monitoring.py` — ежедневный сценарий.
2. `sync_metadata.py` — справочники.
3. `monitoring/find_broken_goals.py` — логика поломки и статусы.
4. `monitoring/periods.py` — длина окна фактов (13 дней).
5. `fetch/fetch_goals_fact.py` — факты из Метрики.
6. `telegram/alert_sender.py` — уведомления.
7. `utils/http_retry.py` — устойчивость запросов к API.

## 13. Запуск с нуля (кратко)

1. DDL + индексы.
2. `agencies` + `.env`.
3. `sync_metadata.py`.
4. `start_monitoring_date` в `ym_goals`.
5. `run_monitoring.py` по расписанию.

Вручную: справочник агентств и даты начала мониторинга. Автоматически: счётчики, цели, факты, статусы и алерты.
