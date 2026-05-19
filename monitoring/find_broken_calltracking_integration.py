from db.db_config import DB_CONFIG
from datetime import datetime, timedelta
from db.db_connection import get_db_connection
from telegram.alert_sender import send_telegram_message


def check_call_goals_without_reaches(db_config):
    today = datetime.now().date()
    period_start = today - timedelta(days=3)  # 3 дня назад (начало периода)
    period_end = today - timedelta(days=1)  # вчерашний день (конец периода)

    print(f"Проверяем срабатывания целей за период с {period_start} по {period_end}")

    with get_db_connection(db_config) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT
                g.id as goal_id,
                g.name as goal_name,
                g.counter_id as counter_id,
                c.name as counter_name,
                MAX(gf.date) as last_reach_date,
                SUM(gf.reaches) as total_reaches
            FROM 
                ym_goals g
            LEFT JOIN
                ym_goals_fact gf
                ON g.id = gf.goal_id
                AND gf.date BETWEEN %s AND %s
            LEFT JOIN
                (SELECT DISTINCT
                    id, 
                    name
                 FROM 
                    ym_counters
                ) AS c
                ON g.counter_id = c.id
            WHERE
                g.type = 'call'
                AND g.start_monitoring_date IS NOT NULL
            GROUP BY
                g.id, g.name, g.counter_id, c.name
        """, (period_start, period_end))

        result = cur.fetchall()

        # Собираем цели без срабатываний за период
        goals_without_reaches = []
        total_goals = 0

        for row in result:
            goal_id, goal_name, counter_id, counter_name, last_reach_date, total_reaches = row
            total_goals += 1

            if total_reaches is None or total_reaches == 0:
                goals_without_reaches.append({
                    'goal_id': goal_id,
                    'goal_name': goal_name,
                    'counter_id': counter_id,
                    'counter_name': counter_name,
                    'last_reach_date': last_reach_date
                })

        # Выводим результаты
        print(f"\nПроверено целей: {total_goals}")
        print(f"Найдено целей без срабатываний: {len(goals_without_reaches)}")
        print(f"Процент целей без срабатываний: {len(goals_without_reaches) / total_goals * 100:.1f}%\n")

        if goals_without_reaches:
            print("Цели типа 'call' без срабатываний за указанный период:")
            print("-" * 80)
            for goal in goals_without_reaches:
                print(f"ID цели: {goal['goal_id']}")
                print(f"Название цели: {goal['goal_name']}")
                print(f"ID счетчика: {goal['counter_id']}")
                print(f"Название счетчика: {goal['counter_name']}")
                if goal['last_reach_date']:
                    print(f"Последнее срабатывание: {goal['last_reach_date']}")
                else:
                    print("Никогда не срабатывала")
                print("-" * 80)
        else:
            print(f"За период с {period_start} по {period_end} все цели типа 'call' имели срабатывания.")