from utils.logger import logger
from psycopg2 import Error as Psycopg2Error
from db.db_connection import get_db_connection

def extract_agencies_info(db_config):
    """Извлекает список названий агентств из таблицы agencies в PostgreSQL.

    Подключается к указанной базе данных, выполняет SQL-запрос и возвращает
    список названий агентств. В случае отсутствия данных вызывает исключение.

    Args:
        db_config (dict): Конфигурация подключения к БД в формате:
            {
                'host': 'адрес_сервера',
                'port': 'порт',
                'dbname': 'имя_БД',
                'user': 'пользователь',
                'password': 'пароль'
            }

    Returns:
        list[tuple]: Список кортежей в формате [(id, name), ...]

    Raises:
        Psycopg2Error: При ошибках работы с PostgreSQL (подключение, запросы).
        ValueError: Если в таблице agencies нет записей.
        Exception: При возникновении непредвиденных ошибок.
    """
    logger.info("Запущена функция по получению названий агентств")

    agencies = []

    try:
        with get_db_connection(db_config) as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, name
                FROM agencies
            """)

            agencies = [(agency[0], agency[1]) for agency in cur.fetchall()]

            if not agencies:
                logger.warning("Не найдено ни одного агентства в базе данных")
                raise ValueError("Не найдено ни одного агентства в базе данных")

            logger.info(f"Успешно получено {len(agencies)} названия агентств")
            return agencies

    except Psycopg2Error as e:
        logger.error(f"Ошибка PostgreSQL: {e}")
        raise

    except Exception as e:
        logger.critical(f"Неизвестная ошибка: {e}")
        raise