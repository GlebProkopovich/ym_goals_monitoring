import os
from datetime import date, timedelta

from dotenv import load_dotenv

from db.db_connection import get_db_connection
from monitoring.periods import facts_date_range
from telegram.alert_sender import GOAL_BLOCK_DELIMITER, send_pipeline_error_alert
from utils.http_retry import format_request_exception_detail, request_with_retry
from utils.logger import logger

load_dotenv()


def _date_range(day_start, day_end):
    current = day_start
    while current <= day_end:
        yield current
        current += timedelta(days=1)


def _build_counter_goals_map(tracking_goals_info):
    """counter_id -> set(goal_id) для целей в мониторинге."""
    counter_goals = {}
    for goal_id, counter_id, _agency_name in tracking_goals_info:
        counter_goals.setdefault(counter_id, set()).add(goal_id)
    return counter_goals


def _get_existing_goal_dates(db_config, goal_ids, day_start, day_end):
    """Множество пар (goal_id, date), которые уже есть в ym_goals_fact."""
    if not goal_ids:
        return set()

    try:
        with get_db_connection(db_config) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT goal_id, date
                FROM ym_goals_fact
                WHERE goal_id = ANY(%s)
                  AND date BETWEEN %s AND %s
                """,
                (list(goal_ids), day_start, day_end),
            )
            return {(row[0], row[1]) for row in cur.fetchall()}
    except Exception as e:
        logger.warning(
            f"Не удалось прочитать факты из БД за период {day_start}–{day_end}: {e}. "
            "Запрашиваем все счётчики через API."
        )
        return set()


def _counter_needs_api_fetch(goal_ids, existing_dates, day_start, day_end):
    """True, если хотя бы одной цели не хватает хотя бы одного дня в периоде."""
    for goal_id in goal_ids:
        for day in _date_range(day_start, day_end):
            if (goal_id, day) not in existing_dates:
                return True
    return False


def fetch_goals_fact(counters, db_config=None, tracking_goals_info=None):
    """
    Получает достижения целей из Яндекс.Метрики за период, нужный для мониторинга
    (13 календарных дней: с «вчера−12» по вчера), только для переданных счётчиков.

    Args:
        counters: [(counter_id, agency_name), ...]
        db_config: конфиг БД для пропуска уже загруженных (goal_id, date)
        tracking_goals_info: [(goal_id, counter_id, agency_name), ...] — фильтр и проверка дыр

    Returns:
        tuple: (list[dict] факты, list[dict] ошибки API по счётчикам)
        Факты: {'date', 'goal_id', 'reaches'}
        Ошибки: {'counter_id', 'agency_name', 'error'}
    """
    logger.info("Запуск функции получения значений достижений целей для счетчиков...")

    end_day = date.today() - timedelta(days=1)
    start_day, _ = facts_date_range(end_day)
    start_date = start_day.strftime("%Y-%m-%d")
    end_date = end_day.strftime("%Y-%m-%d")

    tracking_goal_ids = set()
    counter_goals = {}
    if tracking_goals_info:
        tracking_goal_ids = {row[0] for row in tracking_goals_info}
        counter_goals = _build_counter_goals_map(tracking_goals_info)

    existing_dates = set()
    if db_config and tracking_goal_ids:
        existing_dates = _get_existing_goal_dates(
            db_config, tracking_goal_ids, start_day, end_day
        )
        logger.info(
            f"В БД уже есть {len(existing_dates)} записей (goal_id, date) "
            f"за период {start_date} – {end_date}"
        )

    goals_fact = []
    api_errors = []
    skipped_counters = 0
    fetched_counters = 0

    for counter_id, agency_name in counters:
        token = os.getenv(f"YM_API_TOKEN_{agency_name}")
        if not token:
            logger.warning(
                f"Токен не найден для агентства {agency_name} "
                f"(счётчик {counter_id}) — пропускаем"
            )
            continue

        goals_for_counter = counter_goals.get(counter_id)
        if goals_for_counter and db_config:
            if not _counter_needs_api_fetch(goals_for_counter, existing_dates, start_day, end_day):
                skipped_counters += 1
                logger.info(
                    f"Пропускаем счётчик {counter_id}: все факты за "
                    f"{start_date} – {end_date} уже в БД"
                )
                continue

        url = "https://api-metrika.yandex.net/stat/v1/data"
        params = {
            "ids": counter_id,
            "dimensions": "ym:s:date, ym:s:goal",
            "metrics": "ym:s:anyGoalReaches",
            "date1": start_date,
            "date2": end_date,
            "attribution": "cross_device_last_significant",
            "accuracy": "full",
            "limit": 100000,
        }
        headers = {"Authorization": f"OAuth {token}"}

        try:
            response = request_with_retry("GET", url, headers=headers, params=params, timeout=30)
            data = response.json().get("data", [])
            if not data:
                logger.warning(f"Пустой ответ API для счетчика {counter_id}")
                continue

            fetched_counters += 1
            for row in data:
                try:
                    date_str = row["dimensions"][0]["name"]
                    goal_id = int(row["dimensions"][1]["id"])
                    reaches = int(row["metrics"][0])

                    if tracking_goal_ids and goal_id not in tracking_goal_ids:
                        continue

                    row_date = date.fromisoformat(date_str)
                    if (goal_id, row_date) in existing_dates:
                        continue

                    goals_fact.append({
                        "date": date_str,
                        "goal_id": goal_id,
                        "reaches": reaches,
                    })
                except (KeyError, IndexError, ValueError) as e:
                    logger.warning(
                        f"Некорректная строка API для счетчика {counter_id}: {row}, ошибка: {e}"
                    )

            logger.info(
                f"Получены данные для счетчика {counter_id} за период {start_date} – {end_date}"
            )

        except Exception as e:
            request_context = {
                "url": url,
                "params": {**params, "ids": counter_id},
            }
            detail = format_request_exception_detail(e, request_context=request_context)
            logger.error(f"Ошибка API для счетчика {counter_id} ({agency_name}): {detail}")
            api_errors.append({
                "counter_id": counter_id,
                "agency_name": agency_name,
                "error": detail,
            })

    logger.info(
        f"Факты получены: {len(goals_fact)} новых записей, "
        f"счетчиков из API {fetched_counters}, пропущено (уже в БД) {skipped_counters}, "
        f"ошибок API {len(api_errors)}"
    )
    return goals_fact, api_errors


def _format_counter_api_error(entry: dict) -> str:
    """Один счётчик в сообщении об ошибке: заголовок и детали с отступом."""
    detail = entry["error"].replace("\n", "\n    ")
    return (
        f"  • счётчик {entry['counter_id']} ({entry['agency_name']}):\n"
        f"\n"
        f"    {detail}"
    )


def format_partial_fetch_errors_message(api_errors: list) -> str:
    """Текст алерта при частичном сбое загрузки фактов из API."""
    if not api_errors:
        return ""

    counter_blocks = [_format_counter_api_error(e) for e in api_errors[:20]]
    if len(api_errors) > 20:
        counter_blocks.append(f"  … и ещё {len(api_errors) - 20} счётчиков")
    return (
        "Частичная ошибка загрузки фактов: не удалось получить данные "
        f"для {len(api_errors)} счётчиков:\n"
        "\n"
        + GOAL_BLOCK_DELIMITER.join(counter_blocks)
    )


def failed_counter_ids_from_api_errors(api_errors: list) -> set:
    """ID счётчиков, по которым не удалось получить факты в текущем прогоне."""
    return {e["counter_id"] for e in api_errors if e.get("counter_id") is not None}


def report_partial_fetch_errors(api_errors: list) -> None:
    """Лог и алерт (консоль / Telegram) при частичном сбое fetch_goals_fact."""
    message = format_partial_fetch_errors_message(api_errors)
    if not message:
        return
    logger.error(message)
    send_pipeline_error_alert("fetch_goals_fact (частичный сбой)", message, "")
