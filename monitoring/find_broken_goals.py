from db.db_config import DB_CONFIG
from datetime import datetime, timedelta
from db.db_connection import get_db_connection
from telegram.alert_sender import send_telegram_message


def find_broken_goals(db_config):
    today = datetime.now().date()
    period1_start = today - timedelta(days=10)
    period1_end = today - timedelta(days=4)
    period2_start = today - timedelta(days=3)
    period2_end = today - timedelta(days=1)

    broken_goals = []
    goal_blocks = []

    with get_db_connection(db_config) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT 
                gf.goal_id,
                gf.date,
                gf.reaches,
                g.name AS goal_name,
                c.id AS counter_id,
                c.name AS counter_name,
                a.name AS agency_name
            FROM 
                ym_goals_fact gf
            JOIN ym_goals g ON gf.goal_id = g.id
            JOIN ym_counters c ON g.counter_id = c.id
            JOIN agencies a ON c.agency_id = a.id
            WHERE 
                gf.date BETWEEN %s AND %s
            ORDER BY 
                gf.goal_id, gf.date
        """, (period1_start, period2_end))

        goals_data = {}

        for goal_id, date, reaches, goal_name, counter_id, counter_name, agency_name in cur.fetchall():
            if goal_id not in goals_data:
                goals_data[goal_id] = {
                    'dates': {},
                    'goal_name': goal_name,
                    'counter_id': counter_id,
                    'counter_name': counter_name,
                    'agency_name': agency_name
                }
            goals_data[goal_id]['dates'][date] = reaches

    for goal_id, goal_info in goals_data.items():
        date_reaches = goal_info['dates']

        period1_reaches = sum(
            date_reaches.get(period1_start + timedelta(n), 0)
            for n in range((period1_end - period1_start).days + 1)
        )

        if period1_reaches < 5:
            continue

        period2_reaches = sum(
            date_reaches.get(period2_start + timedelta(n), 0)
            for n in range((period2_end - period2_start).days + 1)
        )

        if period2_reaches == 0:
            broken_goals.append(goal_id)

            block = (
                f"• Агентство: {goal_info['agency_name']}\n"
                f"• Название счетчика: {goal_info['counter_name']}\n"
                f"• ID счетчика: {goal_info['counter_id']}\n"
                f"• Название цели: {goal_info['goal_name']}\n"
                f"• ID цели: {goal_id}\n"
                f"📊 Статистика по периодам:\n"
                f"  ├─ Период 1 ({period1_start} – {period1_end}): {period1_reaches} достижений\n"
                f"  └─ Период 2 ({period2_start} – {period2_end}): {period2_reaches} достижений\n\n"
            )
            goal_blocks.append(block)

    if goal_blocks:
        message_text = (
            "🔍 Обнаружены потенциально сломанные цели:" +
            "\n\n" + ("—" * 30 + "\n\n").join(goal_blocks)
        )
    else:
        message_text = "✅ Все цели работают корректно."

    send_telegram_message(message_text)
    print(message_text)

    return broken_goals