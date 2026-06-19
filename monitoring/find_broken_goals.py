from datetime import datetime, timedelta

from psycopg2.extras import execute_values

from db.db_connection import get_db_connection
from monitoring.periods import facts_date_range
from telegram.alert_sender import notify_console, notify_monitoring
from utils.logger import logger

STATUS_ACTIVE = "active"
STATUS_BROKEN = "broken"
STATUS_INACTIVE = "inactive"
SCREENING_INACTIVE_SUM_MAX = 10

# Категории по сумме срабатываний за эталонные 10 дней (без вчера), после screening
CAT_HIGH = "high"   # эталон high ≥ CAT_HIGH_SUM_MIN — частая, проверка за 1 день
CAT_MID = "mid"     # эталон mid ≥ CAT_MID_SUM_MIN при эталоне high < CAT_HIGH_SUM_MIN — за 2 дня
CAT_LOW = "low"     # эталон mid < CAT_MID_SUM_MIN — редкая, за 3 дня
CAT_HIGH_SUM_MIN = 100
CAT_MID_SUM_MIN = 50

CATEGORY_NAMES = {
    CAT_HIGH: "высокая частота срабатываний",
    CAT_MID: "средняя частота срабатываний",
    CAT_LOW: "низкая частота срабатываний",
}


def _sum_for_days(reaches_by_date, day_start, day_end):
    """Сумма reaches за период [day_start, day_end] включительно."""
    total = 0
    current = day_start
    while current <= day_end:
        total += reaches_by_date.get(current, 0)
        current += timedelta(days=1)
    return total


def _recent_days(yesterday, category):
    """Дни «последнего окна» для проверки поломки/восстановления."""
    if category == CAT_HIGH:
        return [yesterday]
    if category == CAT_MID:
        return [yesterday - timedelta(days=1), yesterday]
    return [yesterday - timedelta(days=2), yesterday - timedelta(days=1), yesterday]


def _recent_sum(reaches_by_date, yesterday, category):
    return sum(reaches_by_date.get(d, 0) for d in _recent_days(yesterday, category))


def _tier_baseline_window(yesterday, tier):
    """
    Эталонные 10 дней для определения категории (без учёта вчера).
    При вчера = 20 мая: high 10–19, mid 9–18, low 8–17.
    """
    if tier == CAT_HIGH:
        return yesterday - timedelta(days=10), yesterday - timedelta(days=1)
    if tier == CAT_MID:
        return yesterday - timedelta(days=11), yesterday - timedelta(days=2)
    return yesterday - timedelta(days=12), yesterday - timedelta(days=3)


def _classify_goal(reaches_by_date, yesterday):
    """
    Возвращает категорию цели или None, если цель не мониторится
    (<= SCREENING_INACTIVE_SUM_MAX за 10 дней с вчера).
    """
    screening_start = yesterday - timedelta(days=9)
    screening_sum = _sum_for_days(reaches_by_date, screening_start, yesterday)
    if screening_sum <= SCREENING_INACTIVE_SUM_MAX:
        return None

    high_start, high_end = _tier_baseline_window(yesterday, CAT_HIGH)
    if _sum_for_days(reaches_by_date, high_start, high_end) >= CAT_HIGH_SUM_MIN:
        return CAT_HIGH

    mid_start, mid_end = _tier_baseline_window(yesterday, CAT_MID)
    if _sum_for_days(reaches_by_date, mid_start, mid_end) >= CAT_MID_SUM_MIN:
        return CAT_MID

    return CAT_LOW


def _format_period(day_start, day_end):
    return f"{day_start} - {day_end}"


def _category_label(category):
    """Человекочитаемое название категории для уведомлений."""
    return CATEGORY_NAMES.get(category, category)


def _load_goals_and_facts(db_config, yesterday):
    """Цели в мониторинге и их факты за нужный диапазон дат."""
    data_start, _data_end = facts_date_range(yesterday)
    goals = {}

    with get_db_connection(db_config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                g.id AS goal_id,
                g.name AS goal_name,
                c.id AS counter_id,
                c.name AS counter_name,
                a.name AS agency_name,
                gf.date,
                gf.reaches
            FROM ym_goals g
            JOIN ym_counters c ON g.counter_id = c.id
            JOIN agencies a ON c.agency_id = a.id
            LEFT JOIN ym_goals_fact gf
                ON g.id = gf.goal_id
                AND gf.date BETWEEN %s AND %s
            WHERE g.start_monitoring_date IS NOT NULL
              AND g.start_monitoring_date <= %s
            ORDER BY g.id, gf.date
            """,
            (data_start, yesterday, yesterday),
        )

        for goal_id, goal_name, counter_id, counter_name, agency_name, fact_date, reaches in cur.fetchall():
            if goal_id not in goals:
                goals[goal_id] = {
                    "goal_name": goal_name,
                    "counter_id": counter_id,
                    "counter_name": counter_name,
                    "agency_name": agency_name,
                    "dates": {},
                }
            if fact_date is not None:
                goals[goal_id]["dates"][fact_date] = reaches

    return goals


def _load_statuses(db_config):
    """Текущие статусы целей: goal_id -> {status, date}."""
    statuses = {}
    with get_db_connection(db_config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT goal_id, status, date
            FROM ym_goals_statuses
            """
        )
        for goal_id, status, status_date in cur.fetchall():
            statuses[goal_id] = {"status": status, "date": status_date}
    return statuses


def _save_statuses_batch(db_config, status_updates):
    """Пакетное сохранение статусов одним подключением к БД."""
    if not status_updates:
        return

    with get_db_connection(db_config) as conn, conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO ym_goals_statuses (date, goal_id, status)
            VALUES %s
            ON CONFLICT (goal_id) DO UPDATE SET
                date = EXCLUDED.date,
                status = EXCLUDED.status
            """,
            status_updates,
            template="(%s, %s, %s)",
        )
        conn.commit()
    logger.info(f"Сохранено/обновлено {len(status_updates)} статусов в ym_goals_statuses")


def _notification_sort_key(goal_info, goal_id):
    """Порядок в уведомлениях: агентство → счётчик → название цели → id цели."""
    return (
        goal_info["agency_name"],
        goal_info["counter_name"],
        goal_info["counter_id"],
        goal_info["goal_name"],
        goal_id,
    )


def _format_goal_block(goal_info, goal_id, category, yesterday, reaches_by_date, event_type):
    baseline_start, baseline_end = _tier_baseline_window(yesterday, category)
    baseline_sum = _sum_for_days(reaches_by_date, baseline_start, baseline_end)
    recent_days = _recent_days(yesterday, category)
    recent_start, recent_end = min(recent_days), max(recent_days)
    recent_sum = sum(reaches_by_date.get(d, 0) for d in recent_days)

    title = "🔴 Цель перестала срабатывать" if event_type == "broken" else "🟢 Цель снова работает"

    return (
        f"{title}\n"
        f"\n"
        f"• Агентство: {goal_info['agency_name']}\n"
        f"• Счётчик: {goal_info['counter_name']} (ID {goal_info['counter_id']})\n"
        f"• Цель: {goal_info['goal_name']} (ID {goal_id})\n"
        f"• Категория: {_category_label(category)}\n"
        f"• Эталонные 10 дней ({_format_period(baseline_start, baseline_end)}): {baseline_sum} срабатываний\n"
        f"• Проверяемое окно ({_format_period(recent_start, recent_end)}): {recent_sum} срабатываний\n\n"
    )


def find_broken_goals(db_config, skip_counter_ids=None):
    """
    Проверяет цели на поломку и восстановление, сохраняет статусы в ym_goals_statuses,
    выводит уведомления в консоль; Telegram — при TELEGRAM_ENABLED=true.
    Цели с <= SCREENING_INACTIVE_SUM_MAX срабатываний получают статус inactive без уведомлений.
    Если передан skip_counter_ids, цели этих счётчиков полностью исключаются из проверки
    на текущий прогон (например, при частичном сбое загрузки фактов из API).
    """
    yesterday = datetime.now().date() - timedelta(days=1)
    logger.info(f"Старт мониторинга целей, последний учитываемый день: {yesterday}")

    goals = _load_goals_and_facts(db_config, yesterday)
    skip_counter_ids = set(skip_counter_ids or [])
    if skip_counter_ids:
        goals = {
            goal_id: goal_info
            for goal_id, goal_info in goals.items()
            if goal_info["counter_id"] not in skip_counter_ids
        }
        logger.warning(
            "Проверка сломанных целей частично пропущена: "
            f"{len(skip_counter_ids)} счётчиков с ошибкой API; "
            f"список счётчиков: {sorted(skip_counter_ids)}"
        )
    statuses = _load_statuses(db_config)

    broken_entries = []
    recovered_entries = []
    broken_goal_ids = []
    status_updates = []

    for goal_id, goal_info in goals.items():
        reaches_by_date = goal_info["dates"]
        category = _classify_goal(reaches_by_date, yesterday)

        prev = statuses.get(goal_id)
        prev_status = prev["status"] if prev else None

        if category is None:
            if prev_status != STATUS_INACTIVE:
                status_updates.append((yesterday, goal_id, STATUS_INACTIVE))
                logger.info(
                    f"Цель {goal_id}: <= {SCREENING_INACTIVE_SUM_MAX} срабатываний за 10 дней с вчера, "
                    f"статус inactive (без уведомления)"
                )
            continue

        recent_sum = _recent_sum(reaches_by_date, yesterday, category)
        is_broken = recent_sum == 0
        is_recovered = prev_status == STATUS_BROKEN and recent_sum >= 1

        if is_broken:
            if prev_status != STATUS_BROKEN:
                broken_goal_ids.append(goal_id)
                broken_entries.append((
                    _notification_sort_key(goal_info, goal_id),
                    _format_goal_block(
                        goal_info, goal_id, category, yesterday, reaches_by_date, "broken"
                    ),
                ))
                logger.info(f"Цель {goal_id}: поломка, вывод в консоль")
            else:
                logger.info(f"Цель {goal_id}: по-прежнему сломана, уведомление не дублируем")

            status_updates.append((yesterday, goal_id, STATUS_BROKEN))

        elif is_recovered:
            recovered_entries.append((
                _notification_sort_key(goal_info, goal_id),
                _format_goal_block(
                    goal_info, goal_id, category, yesterday, reaches_by_date, "recovered"
                ),
            ))
            status_updates.append((yesterday, goal_id, STATUS_ACTIVE))
            logger.info(f"Цель {goal_id}: восстановлена, вывод в консоль")

        else:
            if prev_status != STATUS_ACTIVE:
                status_updates.append((yesterday, goal_id, STATUS_ACTIVE))
                if prev_status is not None:
                    logger.info(f"Цель {goal_id}: статус обновлён на active")
            # Уже active — в таблице ничего не меняем (кроме случая восстановления выше)

    _save_statuses_batch(db_config, status_updates)

    broken_entries.sort(key=lambda item: item[0])
    recovered_entries.sort(key=lambda item: item[0])
    broken_notifications = [text for _, text in broken_entries]
    recovered_notifications = [text for _, text in recovered_entries]

    if broken_notifications:
        broken_text = (
            "🔍 Обнаружены потенциально сломанные цели:\n\n"
            + ("—" * 30 + "\n\n").join(broken_notifications)
        )
        notify_monitoring(broken_text)
    else:
        notify_monitoring("✅ Сломанных целей не обнаружено.")

    if recovered_notifications:
        recovered_text = (
            "✅ Цели снова начали срабатывать:\n\n"
            + ("—" * 30 + "\n\n").join(recovered_notifications)
        )
        notify_console(recovered_text)
        logger.info(recovered_text)

    logger.info(
        f"Мониторинг завершён: сломанных (новых) {len(broken_goal_ids)}, "
        f"восстановленных {len(recovered_notifications)}"
    )
    return broken_goal_ids
