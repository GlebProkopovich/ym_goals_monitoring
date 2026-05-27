"""
Ежедневный мониторинг: факты достижений → проверка поломок → уведомления.
"""

import sys

from db.db_config import DB_CONFIG
from extract.extract_tracking_goals_info import (
    extract_counters_for_tracking_goals,
    extract_tracking_goals_info,
)
from fetch.fetch_goals_fact import fetch_goals_fact
from monitoring.find_broken_goals import find_broken_goals
from save.save_goals_fact_to_db import save_goals_fact_to_db
from telegram.alert_sender import send_pipeline_error_alert
from utils.logger import logger
from utils.metrika_api_counter import log_metrika_api_daily_usage
from utils.pipeline_errors import run_stage


def _report_api_errors(api_errors: list) -> None:
    if not api_errors:
        return
    lines = [
        f"  • счётчик {e['counter_id']} ({e['agency_name']}): {e['error']}"
        for e in api_errors[:20]
    ]
    if len(api_errors) > 20:
        lines.append(f"  … и ещё {len(api_errors) - 20} счётчиков")
    message = (
        f"Частичная ошибка загрузки фактов: не удалось получить данные "
        f"для {len(api_errors)} счётчиков:\n" + "\n".join(lines)
    )
    logger.error(message)
    send_pipeline_error_alert("fetch_goals_fact (частичный сбой)", message, "")


def main() -> int:
    try:
        tracking_goals_info = run_stage(
            "извлечение целей в мониторинге",
            lambda: extract_tracking_goals_info(DB_CONFIG),
        )
        counters_for_facts = extract_counters_for_tracking_goals(tracking_goals_info)

        all_goals_fact, api_errors = run_stage(
            "загрузка фактов из API",
            lambda: fetch_goals_fact(
                counters_for_facts, DB_CONFIG, tracking_goals_info
            ),
        )
        _report_api_errors(api_errors)
        log_metrika_api_daily_usage("run_monitoring, после загрузки фактов")

        run_stage(
            "сохранение фактов в БД",
            lambda: save_goals_fact_to_db(DB_CONFIG, all_goals_fact),
        )
        run_stage("проверка сломанных целей", lambda: find_broken_goals(DB_CONFIG))

        logger.info("Мониторинг завершён успешно")
        log_metrika_api_daily_usage("run_monitoring")
        return 0
    except Exception:
        log_metrika_api_daily_usage("run_monitoring (с ошибкой)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
