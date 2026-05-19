# ym_goals_monitoring

Python-проект для мониторинга целей Яндекс.Метрики с сохранением данных в PostgreSQL и отправкой уведомлений в Telegram.

Проект реализует ETL-процесс и слой мониторинга:
- извлекает справочные данные из БД;
- получает фактические достижения целей из API Яндекс.Метрики;
- сохраняет факты в БД;
- ищет аномалии в динамике достижений;
- отправляет алерты в Telegram.

## 1. Цель проекта

Автоматически находить потенциально "сломанные" цели Яндекс.Метрики: те, которые раньше стабильно срабатывали, но в последние дни перестали приносить достижения.

## 2. Текущий статус реализации

На текущий момент реализован основной контур мониторинга:
1) загрузка фактов достижений целей из Метрики;
2) фильтрация только по целям, допущенным к мониторингу;
3) запись фактов в PostgreSQL;
4) проверка аномалий;
5) отправка уведомления в Telegram.

Дополнительно реализованы функции для синхронизации справочников (агентства -> счетчики -> цели), но они пока не собраны в отдельный исполняемый pipeline.

## 3. Структура проекта

```text
ym_goals_monitoring/
├─ pipeline.py
├─ requirements.txt
├─ db/
│  ├─ db_config.py
│  └─ db_connection.py
├─ extract/
│  ├─ extract_agencies_info.py
│  ├─ extract_counters.py
│  ├─ extract_goals_info.py
│  └─ extract_tracking_goals_info.py
├─ fetch/
│  ├─ fetch_counters.py
│  ├─ fetch_goals_info.py
│  └─ fetch_goals_fact.py
├─ transform/
│  └─ filter_goals_fact.py
├─ save/
│  ├─ save_counters_to_db.py
│  ├─ save_goals_info_to_db.py
│  └─ save_goals_fact_to_db.py
├─ monitoring/
│  ├─ find_broken_goals.py
│  └─ find_broken_calltracking_integration.py
├─ telegram/
│  └─ alert_sender.py
└─ utils/
   └─ logger.py
```

## 4. Основной рабочий поток (`pipeline.py`)

`pipeline.py` - текущая главная точка входа.

Порядок выполнения:

1. `extract_counters(DB_CONFIG)`
   - читает из БД список счетчиков и соответствующих агентств;
   - возвращает `[(counter_id, agency_name), ...]`.

2. `fetch_goals_fact(counters)`
   - ходит в `stat/v1/data` Яндекс.Метрики;
   - получает достижения по всем целям каждого счетчика;
   - период: от `today - 61 day` до `yesterday`;
   - возвращает список словарей:
     `{'date': 'YYYY-MM-DD', 'goal_id': int, 'reaches': int}`.

3. `extract_tracking_goals_info(DB_CONFIG)`
   - читает из БД цели, у которых `start_monitoring_date <= CURRENT_DATE`;
   - возвращает кортежи `(goal_id, counter_id, agency_name)`.

4. `filter_goals_fact(all_goals_fact, tracking_goals_info)`
   - отсекает факты по целям, которые не должны мониториться;
   - оставляет только записи, где `goal_id` входит в мониторинговый список.

5. `save_goals_fact_to_db(DB_CONFIG, filtered_goals_fact)`
   - пакетно пишет данные в `ym_goals_fact`;
   - `ON CONFLICT (date, goal_id) DO UPDATE reaches`.

6. `find_broken_goals(DB_CONFIG)`
   - анализирует динамику достижений;
   - формирует уведомление;
   - отправляет его в Telegram.

## 5. Логика определения "сломанных" целей

Реализована в `monitoring/find_broken_goals.py`.

Алгоритм:
- Период 1: с `today-10` по `today-4` (7 дней).
- Период 2: с `today-3` по `today-1` (3 дня).

Цель считается потенциально сломанной, если:
1) сумма достижений в Периоде 1 >= 5;
2) сумма достижений в Периоде 2 == 0.

Если найдены такие цели, в Telegram отправляется блок с деталями:
- название/ID цели;
- название/ID счетчика;
- агентство;
- статистика по двум периодам.

Если не найдены - отправляется сообщение, что все цели работают корректно.

## 6. Работа с базой данных

### 6.1 Конфигурация подключения

`db/db_config.py` формирует `DB_CONFIG` из `.env`:
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_SCHEMA` (через `options: -c search_path=...`)

`db/db_connection.py` использует `psycopg2.connect(**db_config, connect_timeout=10)`.

### 6.2 Таблицы, которые участвуют в работе

По SQL-запросам проекта используются:

1. `agencies`
   - поля минимум: `id`, `name`.

2. `ym_counters`
   - поля минимум: `id`, `name`, `agency_id`.

3. `ym_goals`
   - поля минимум: `id`, `counter_id`, `type`, `name`, `start_monitoring_date`.

4. `ym_goals_fact`
   - поля минимум: `date`, `goal_id`, `reaches`.

### 6.3 Логические связи

- `agencies (1) -> (N) ym_counters` по `agency_id`.
- `ym_counters (1) -> (N) ym_goals` по `counter_id`.
- `ym_goals (1) -> (N) ym_goals_fact` по `goal_id`.

### 6.4 Важные ограничения/конфликты

Код ожидает, что есть соответствующие уникальные ключи:
- для `ym_goals_fact`: `(date, goal_id)`;
- для `ym_counters`: `(id, agency_id)`;
- для `ym_goals`: `(id)`.

## 7. Интеграция с API Яндекс.Метрики

### 7.1 Получение счетчиков

`fetch/fetch_counters.py`:
- endpoint: `https://api-metrika.yandex.net/management/v1/counters`;
- вход: список агентств `[(agency_id, agency_name), ...]`;
- для каждого агентства берется токен `YM_API_TOKEN_<agency_name>`;
- каждому счетчику добавляется `agency_id` перед сохранением.

### 7.2 Получение целей

`fetch/fetch_goals_info.py`:
- endpoint: `https://api-metrika.yandex.net/management/v1/counter/{counter_id}/goals`;
- вход: список счетчиков `[(counter_id, agency_name), ...]`;
- токен: `YM_API_TOKEN_<agency_name>`;
- выход: список целей (`counter_id`, `goal_id`, `type`, `name`).

### 7.3 Получение фактов достижений целей

`fetch/fetch_goals_fact.py`:
- endpoint: `https://api-metrika.yandex.net/stat/v1/data`;
- dimensions: `ym:s:date, ym:s:goal`;
- metrics: `ym:s:sumGoalReachesAny`;
- attribution: `cross_device_last_significant`;
- accuracy: `full`;
- период: последние 61 день до вчера.

## 8. Telegram-уведомления

`telegram/alert_sender.py`:
- загружает `.env` через `load_dotenv()`;
- читает:
  - `TELEGRAM_TOKEN`
  - `TELEGRAM_CHAT_ID`;
- отправляет сообщение в Bot API `sendMessage`.

Если переменные Telegram отсутствуют, модуль поднимает ошибку уже на этапе импорта.

## 9. Логирование

`utils/logger.py` настраивает глобальный логгер:
- уровень: `INFO`;
- запись в `logs/project.log`;
- вывод в консоль.

Каталог `logs/` создается автоматически.

## 10. Реализованные, но не подключенные в основной pipeline сценарии

В проекте есть готовые функции, которые не вызываются из `pipeline.py`:

1) Синхронизация счетчиков:
- `extract_agencies_info(db_config)` -> `fetch_counters(agencies_info)` -> `save_counters_to_db(db_config, counters)`.

2) Синхронизация целей:
- `extract_counters(db_config)` или `extract_goals_info(db_config)` + `fetch_goals_info(counters)` -> `save_goals_to_db(db_config, goals_data)`.

3) Дополнительная проверка calltracking:
- `monitoring/find_broken_calltracking_integration.py` -> `check_call_goals_without_reaches(db_config)`;
- проверяет цели типа `call` без срабатываний за последние 3 дня;
- выводит отчет в консоль.

## 11. Переменные окружения (`.env`)

Минимально ожидаются:

```dotenv
DB_HOST=...
DB_PORT=...
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_SCHEMA=...

TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...

# Для каждого агентства по имени из таблицы agencies:
YM_API_TOKEN_<AGENCY_NAME>=...
```

Примечание: так как токен выбирается как `YM_API_TOKEN_{agency_name}`, имя агентства в БД должно соответствовать шаблону env-переменной.

## 12. Установка и запуск

### 12.1 Установка зависимостей

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 12.2 Запуск текущего мониторинга

```bash
python pipeline.py
```

### 12.3 Что проверить после запуска

1) Логи в `logs/project.log`.
2) Появились/обновились записи в `ym_goals_fact`.
3) В Telegram пришло сообщение с результатом мониторинга.

## 13. Карта по файлам: "где что смотреть"

Если хочешь быстро восстановить контекст по коду:

1. `pipeline.py` - общий сценарий и порядок шагов.
2. `monitoring/find_broken_goals.py` - критерии поломки и формат алерта.
3. `fetch/fetch_goals_fact.py` - запросы фактов в Метрику.
4. `save/save_goals_fact_to_db.py` - запись фактов в БД.
5. `extract/extract_tracking_goals_info.py` + `transform/filter_goals_fact.py` - что именно мониторится.
6. `telegram/alert_sender.py` - доставка уведомлений.
7. `db/db_config.py` + `db/db_connection.py` - подключение к БД.
8. `fetch/fetch_counters.py`, `fetch/fetch_goals_info.py`, `save/save_counters_to_db.py`, `save/save_goals_info_to_db.py` - контур синхронизации справочников.
9. `monitoring/find_broken_calltracking_integration.py` - дополнительная диагностическая проверка call-целей.

## 14. Текущие ограничения и зоны для доработки

1) Нет отдельного entrypoint для синхронизации справочников (счетчики/цели).
2) Нет автоматизации запуска (cron/task scheduler/Airflow) в репозитории.
3) Нет тестов.
4) В `fetch_goals_fact` при отсутствии токена нет явной проверки до запроса.
5) В `find_broken_calltracking_integration` возможен `ZeroDivisionError`, если `total_goals == 0`.
6) Использование схемы БД местами неоднородно (где-то через `search_path`, где-то с явным префиксом схемы).

---

Если ты будешь проходить код "с нуля", рекомендую порядок:
`pipeline.py` -> `fetch_goals_fact.py` -> `extract_tracking_goals_info.py` -> `filter_goals_fact.py` -> `save_goals_fact_to_db.py` -> `find_broken_goals.py` -> остальные модули синхронизации.

## 15. Мануал: запуск с нуля (если в БД вообще нет таблиц)

Ниже практический чеклист для старта проекта "с чистого листа".

### 15.1 Что нужно создать в БД вручную

Создать нужно все 4 таблицы:
- `agencies`
- `ym_counters`
- `ym_goals`
- `ym_goals_fact`

Пример минимального DDL под текущую логику кода:

```sql
-- 1) Агентства (ручной справочник)
CREATE TABLE IF NOT EXISTS agencies (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

-- 2) Счетчики Метрики
CREATE TABLE IF NOT EXISTS ym_counters (
    id BIGINT NOT NULL,
    name TEXT NOT NULL,
    agency_id BIGINT NOT NULL REFERENCES agencies(id),
    PRIMARY KEY (id, agency_id)
);

-- 3) Цели Метрики
CREATE TABLE IF NOT EXISTS ym_goals (
    id BIGINT PRIMARY KEY,
    counter_id BIGINT NOT NULL,
    type TEXT,
    name TEXT NOT NULL,
    start_monitoring_date DATE NULL
);

-- 4) Факты достижений целей по датам
CREATE TABLE IF NOT EXISTS ym_goals_fact (
    date DATE NOT NULL,
    goal_id BIGINT NOT NULL REFERENCES ym_goals(id),
    reaches BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (date, goal_id)
);
```

### 15.2 Что заполняется вручную

Вручную обязательно:
1) `agencies` - справочник агентств (`id`, `name`);
2) `.env` - токены для агентств (`YM_API_TOKEN_<agency_name>`);
3) `ym_goals.start_monitoring_date` - дата начала мониторинга для целей, которые нужно контролировать.

Пример первичного заполнения агентств:

```sql
INSERT INTO agencies (id, name) VALUES
(1, 'AGENCY1'),
(2, 'AGENCY2');
```

Важно: имя агентства в `agencies.name` должно совпадать с суффиксом переменной в `.env`, потому что токен берется по шаблону `YM_API_TOKEN_{agency_name}`.

### 15.3 Что формируется автоматически кодом

Автоматически (функции в проекте уже есть):
- `ym_counters` - через `fetch_counters` + `save_counters_to_db`;
- `ym_goals` - через `fetch_goals_info` + `save_goals_to_db`;
- `ym_goals_fact` - через основной `pipeline.py`.

### 15.4 Что уже работает в текущем `pipeline.py`

При запуске `python pipeline.py` автоматически:
1) берутся счетчики из БД;
2) тянутся факты достижений из Метрики;
3) факты фильтруются по целям в мониторинге;
4) `ym_goals_fact` обновляется (upsert);
5) отправляется Telegram-алерт.

При этом в текущем `pipeline.py` не встроена автоматическая синхронизация `ym_counters` и `ym_goals` (хотя функции для этого есть).

### 15.5 Рекомендуемый порядок действий после "чистого старта"

1) Создать 4 таблицы SQL-скриптом выше.
2) Заполнить `agencies`.
3) Настроить `.env` (`DB_*`, `TELEGRAM_*`, `YM_API_TOKEN_*`).
4) Один раз выполнить синхронизацию справочников (счетчики и цели) отдельным скриптом/ручной связкой функций.
5) Проставить `start_monitoring_date` у нужных целей в `ym_goals`.
6) Запускать `python pipeline.py` регулярно.

Итог в одном предложении: вручную поддерживается бизнес-справочник (`agencies`) и флаг включения в мониторинг (`start_monitoring_date`), а факты и технические данные по целям/счетчикам могут формироваться автоматически.

__________________________________

Заметки

Рассмотреть вариант с квантилями, поможет убрать всплески
Подумать о логике учета вала количества достижений . Например если за 10 дней 100+ достижений, то можно в учет брать только 1 последний день, если меньше 5, то 3 дня
Нужно подумать о конверсиях
Об отклонениях на тотал уровне. ПРосадка на % от среднего (возможно медиана)
Подумать о том как сократить кол-во повторений отправки уведомлений по одной цели. Может добавить уведомление, что цель заработала?
Возможно нужна доп таблица где будем хранить статус по проверке и её проверять прежде чем слать уведомление
Можно ли один аккаунт Cursor юзать на нескольких? Возможно оплата
Пока мониторинг для нас, коллег не впускать

--- Срок: отпуск, 18-22 - проверка - ур-нь 1 проверка сломалась ли цель, 25-29 - на аномалии, 1-7(для нас) - отключить шум. Можно подключить Валентина. Можно выключить ненужные счетчики. Действовать лучше по принципу ЧС (выключаем, а не выключаем). 