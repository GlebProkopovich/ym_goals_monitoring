from utils.logger import logger
from db.db_connection import get_db_connection


def extract_counters(db_config):
    """Извлекает список счетчиков Яндекс.Метрики с привязанными агентствами из базы данных.

    Подключается к указанной базе данных и выполняет SQL-запрос для получения списка
    уникальных связок (id счетчика, название агентства) из таблиц ym_counters и agencies.

    Args:
        db_config (dict): Конфигурация подключения к БД, содержащая параметры:
            - host (str): Хост БД
            - port (int): Порт БД
            - database (str): Имя базы данных
            - user (str): Имя пользователя
            - password (str): Пароль пользователя

    Returns:
        list[tuple]: Список кортежей, где каждый кортеж содержит:
            - counter_id (int): ID счетчика Яндекс.Метрики
            - agency_name (str): Название агентства, к которому привязан счетчик
    """
    logger.info("Извлечение списка счетчиков Яндекс.Метрики с привязанными агентствами из базы данных...")

    counters = []

    with get_db_connection(db_config) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT
                c.id as counter_id, 
                a.name as agency_name
            FROM 
                ym_counters c
            JOIN
                agencies a
            ON
                c.agency_id = a.id
        """)

        results = cur.fetchall()
        for row in results:
            counters.append(row)

    logger.info(f"Извлечено {len(counters)} счетчиков")

    return counters