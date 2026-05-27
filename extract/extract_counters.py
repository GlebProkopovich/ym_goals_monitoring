from utils.logger import logger
from db.db_connection import get_db_connection


def extract_counters(db_config=None, *, api_counters=None):
    """
    Возвращает список счётчиков в формате [(counter_id, agency_name), ...].

    Режимы:
    - api_counters задан — подготовка списка из ответа API (для sync_metadata);
    - иначе — чтение всех счётчиков из БД (ym_counters + agencies).
    """
    if api_counters is not None:
        logger.info("Подготовка списка счётчиков из ответа API...")
        counters = [(counter["id"], counter["agency_name"]) for counter in api_counters]
        logger.info(f"Подготовлено {len(counters)} счётчиков из API")
        return counters

    if db_config is None:
        raise ValueError("Нужен db_config, если api_counters не передан")

    logger.info(
        "Извлечение списка счетчиков Яндекс.Метрики с привязанными агентствами из базы данных..."
    )

    counters = []

    with get_db_connection(db_config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT
                c.id AS counter_id,
                a.name AS agency_name
            FROM ym_counters c
            JOIN agencies a ON c.agency_id = a.id
            """
        )

        for row in cur.fetchall():
            counters.append(row)

    logger.info(f"Извлечено {len(counters)} счетчиков из БД")
    return counters
