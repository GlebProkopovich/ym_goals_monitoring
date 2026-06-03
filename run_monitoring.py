"""
Ежедневный мониторинг: факты достижений → проверка поломок → уведомления.
"""

import sys

from db.db_config import DB_CONFIG
from extract.extract_tracking_goals_info import (
    extract_counters_for_tracking_goals,
    extract_tracking_goals_info,
)
from fetch.fetch_goals_fact import (
    failed_counter_ids_from_api_errors,
    fetch_goals_fact,
    report_partial_fetch_errors,
)
from monitoring.find_broken_goals import find_broken_goals
from save.save_goals_fact_to_db import save_goals_fact_to_db
from utils.logger import logger
from utils.metrika_api_counter import log_metrika_api_daily_usage
from utils.pipeline_errors import run_stage


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
        failed_counter_ids = failed_counter_ids_from_api_errors(api_errors)
        report_partial_fetch_errors(api_errors)
        if failed_counter_ids:
            logger.warning(
                "Проверка сломанных целей будет частично пропущена: "
                f"{len(failed_counter_ids)} счётчиков с ошибкой API"
            )
        log_metrika_api_daily_usage("run_monitoring, после загрузки фактов")

        run_stage(
            "сохранение фактов в БД",
            lambda: save_goals_fact_to_db(DB_CONFIG, all_goals_fact),
        )
        run_stage(
            "проверка сломанных целей",
            lambda: find_broken_goals(DB_CONFIG, skip_counter_ids=failed_counter_ids),
        )

        logger.info("Мониторинг завершён успешно")
        log_metrika_api_daily_usage("run_monitoring")
        return 0
    except Exception:
        log_metrika_api_daily_usage("run_monitoring (с ошибкой)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
