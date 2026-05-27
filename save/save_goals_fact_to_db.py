from utils.logger import logger
from psycopg2.extras import execute_values
from db.db_connection import get_db_connection


def save_goals_fact_to_db(db_config, goals_fact):
    """
    Сохраняет достижения целей в базу данных. Если запись с указанной датой и goal_id уже существует,
    то обновляет значение 'reaches'.

    :param db_config: Конфигурация для подключения к базе данных
    :param goals_fact: Список словарей, каждый из которых содержит данные о достижении цели с ключами:
                       'date', 'goal_id', 'reaches'.
    """
    if not goals_fact:
        logger.warning("Пустой список фактов — сохранение пропущено")
        return

    try:
        with get_db_connection(db_config) as conn, conn.cursor() as cur:
            logger.info("Соединение с базой данных установлено.")

            # Подготовка данных для пакетной вставки
            values = [(item['date'], item['goal_id'], item['reaches']) for item in goals_fact]

            query = """
                INSERT INTO ym_goals_fact (date, goal_id, reaches)
                VALUES %s
                ON CONFLICT (date, goal_id) DO UPDATE
                SET reaches = EXCLUDED.reaches
            """

            execute_values(cur, query, values)
            conn.commit()
            logger.info(f"Успешно сохранено или обновлено {len(values)} записей в ym_goals_fact.")

    except Exception as e:
        logger.error(f"Ошибка при пакетной вставке данных: {e}")
        raise
