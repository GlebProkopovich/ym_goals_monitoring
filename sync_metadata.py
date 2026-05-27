"""
Синхронизация справочников: агентства → счётчики → цели.
Запускать периодически (например, раз в неделю), не каждый день мониторинга.
"""

import sys

from db.db_config import DB_CONFIG
from extract.extract_agencies_info import extract_agencies_info
from extract.extract_counters import extract_counters
from fetch.fetch_counters import fetch_counters
from fetch.fetch_goals_info import fetch_goals_info
from save.save_counters_to_db import save_counters_to_db
from save.save_goals_info_to_db import save_goals_to_db
from sync.log_stale_counters import (
    find_stale_counters_in_db,
    log_counters_missing_from_api,
    log_goals_skipped_for_stale_counters,
)
from utils.logger import logger
from utils.metrika_api_counter import log_metrika_api_daily_usage
from utils.pipeline_errors import run_stage


def main() -> int:
    try:
        agencies = run_stage("извлечение агентств", lambda: extract_agencies_info(DB_CONFIG))
        counters, fetched_agency_ids = run_stage(
            "загрузка счётчиков из API", lambda: fetch_counters(agencies)
        )
        run_stage("сохранение счётчиков", lambda: save_counters_to_db(DB_CONFIG, counters))

        stale_counters = find_stale_counters_in_db(
            DB_CONFIG, counters, fetched_agency_ids
        )
        log_counters_missing_from_api(stale_counters)
        log_goals_skipped_for_stale_counters(stale_counters)

        counters_for_goals = run_stage(
            "подготовка счётчиков для загрузки целей",
            lambda: extract_counters(api_counters=counters),
        )
        goals_info = run_stage(
            "загрузка целей из API",
            lambda: fetch_goals_info(counters_for_goals),
        )
        run_stage("сохранение целей", lambda: save_goals_to_db(DB_CONFIG, goals_info))

        logger.info("Синхронизация справочников завершена успешно")
        log_metrika_api_daily_usage("sync_metadata")
        return 0
    except Exception:
        log_metrika_api_daily_usage("sync_metadata (с ошибкой)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
