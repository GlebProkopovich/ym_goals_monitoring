"""Счётчики из БД, которых нет в ответе API (вероятно отозван доступ)."""

from db.db_connection import get_db_connection
from utils.logger import logger


def _api_counter_ids_by_agency(api_counters):
    """agency_id -> множество id счётчиков из ответа API."""
    by_agency = {}
    for counter in api_counters:
        agency_id = counter["agency_id"]
        by_agency.setdefault(agency_id, set()).add(counter["id"])
    return by_agency


def find_stale_counters_in_db(db_config, api_counters, fetched_agency_ids):
    """
    Счётчики в БД по агентствам с успешным ответом API, которых нет в этом ответе.

    Returns:
        list[dict]: {"id", "name", "agency_name"}
    """
    if not fetched_agency_ids:
        return []

    api_ids_by_agency = _api_counter_ids_by_agency(api_counters)
    stale = []

    with get_db_connection(db_config) as conn, conn.cursor() as cur:
        for agency_id in fetched_agency_ids:
            cur.execute(
                """
                SELECT c.id, c.name, a.name AS agency_name
                FROM ym_counters c
                JOIN agencies a ON c.agency_id = a.id
                WHERE c.agency_id = %s
                """,
                (agency_id,),
            )
            api_ids = api_ids_by_agency.get(agency_id, set())

            for counter_id, counter_name, agency_name in cur.fetchall():
                if counter_id not in api_ids:
                    stale.append({
                        "id": counter_id,
                        "name": counter_name,
                        "agency_name": agency_name,
                    })

    return stale


def log_counters_missing_from_api(stale_counters):
    """Лог: счётчик есть в БД, но не вернулся из API."""
    if not stale_counters:
        logger.info(
            "Все счётчики в БД для проверенных агентств присутствуют в ответе API"
        )
        return

    for counter in stale_counters:
        logger.warning(
            f"Счётчик {counter['id']} («{counter['name']}»), агентство {counter['agency_name']}: "
            f"есть в БД, но не вернулся из API — вероятно, доступ к счётчику отозван"
        )
    logger.warning(
        f"Всего счётчиков в БД без ответа в API: {len(stale_counters)}"
    )


def log_goals_skipped_for_stale_counters(stale_counters):
    """Лог: цели по счётчику не запрашивались из-за отсутствия в ответе API."""
    if not stale_counters:
        return

    for counter in stale_counters:
        logger.warning(
            f"Цели для счётчика {counter['id']} («{counter['name']}»), "
            f"агентство {counter['agency_name']}: не запрашивались — "
            f"вероятно, доступ к счётчику отозван"
        )
    logger.warning(
        f"Запрос целей пропущен для {len(stale_counters)} счётчиков (нет в ответе API)"
    )
