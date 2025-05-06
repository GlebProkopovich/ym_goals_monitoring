import psycopg2
from utils.logger import logger


def get_db_connection(db_config):
    """
    Устанавливает соединение с PostgreSQL базой данных по переданной конфигурации.

    Args:
        db_config (dict): Конфигурация подключения. Обязательные ключи:
            host, port, dbname, user, password.

    Returns:
        psycopg2.connection: Активное соединение с БД.

    Raises:
        ValueError: Если конфиг неполный.
        psycopg2.OperationalError: При ошибках подключения.
    """
    try:
        conn = psycopg2.connect(**db_config, connect_timeout=10)
        logger.info('Подключение к БД установлено успешно')
        return conn
    except Exception as e:
        logger.error(f"Возникла ошибка, при подключении к БД: {e}")
        raise