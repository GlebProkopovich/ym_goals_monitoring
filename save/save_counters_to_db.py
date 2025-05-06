from utils.logger import logger
from db.db_connection import get_db_connection


def save_counters_to_db(db_config, counters):
    """
    Сохраняет список счетчиков в базу данных.

    Args:
        db_config (dict): Конфигурация подключения к БД
        counters (list): Список словарей с данными счетчиков

    Raises:
        Exception: При ошибках работы с БД
    """
    try:
        with get_db_connection(db_config) as conn, conn.cursor() as cur:
            data = [
                (counter['id'], counter['name'], counter['agency_id'])
                for counter in counters
            ]

            cur.executemany("""
                INSERT INTO ym_counters 
                    (id, name, agency_id) 
                VALUES 
                    (%s, %s, %s)
                ON CONFLICT (id, agency_id) DO UPDATE SET
                    name = EXCLUDED.name
            """, data)
            conn.commit()
            logger.info(f"Успешно добавлено {len(data)} счетчиков в БД")

    except Exception as e:
        logger.error(f"Ошибка при сохранении счетчиков в БД: {str(e)}")
        raise