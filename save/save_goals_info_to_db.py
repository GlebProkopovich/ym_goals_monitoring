from utils.logger import logger
from db.db_connection import get_db_connection


def save_goals_to_db(db_config, goals_data):
    """
    Сохраняет список целей Яндекс.Метрики в базу данных.

    Args:
        db_config: Конфигурация подключения к базе данных.
        goals_data: Список словарей с информацией о целях.
                    Формат: [
                        {
                            'counter_id': int,
                            'goal_id': int,
                            'type': str,
                            'name': str
                        },
                        ...
                    ]

    Поведение:
        - Вставляет новые цели в таблицу ym_goals.
        - Пропускает цели с повторяющимся goal_id.
        - Логгирует количество добавленных целей.
    """
    logger.info("Начато сохранение целей в базу данных...")

    if not goals_data:
        logger.warning("Пустой список целей — сохранение пропущено")
        return

    with get_db_connection(db_config) as conn, conn.cursor() as cur:
        data = []
        for goal in goals_data:
            try:
                data.append((
                    goal['goal_id'],
                    goal['counter_id'],
                    goal['type'],
                    goal['name']
                ))
            except KeyError as e:
                logger.error(f"Пропущена цель из-за отсутствующего ключа: {e}")
                continue

        if not data:
            logger.warning("Нет валидных целей для добавления в базу данных")
            return

        cur.executemany("""
            INSERT INTO
                ym_goals (id, counter_id, type, name, start_monitoring_date)
            VALUES
                (%s, %s, %s, %s, NULL)
            ON CONFLICT (id) DO UPDATE SET
                type = EXCLUDED.type,
                name = EXCLUDED.name
        """, data)
        conn.commit()

        logger.info(f"Успешно добавлено/обновлено {len(data)} записей в таблице ym_goals")