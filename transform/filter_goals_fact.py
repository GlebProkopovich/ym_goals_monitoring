def filter_goals_fact(goals_fact, tracking_goals_info):
    """
    Фильтрует список достижений целей, оставляя только те, которые есть в списке отслеживаемых целей.

    :param goals_fact: список словарей, каждый с ключами: date, goal_id, reaches
    :param tracking_goals_info: список кортежей (goal_id, counter_id, agency_name)
    :return: отфильтрованный список словарей с ключами: date, goal_id, reaches
    """
    tracking_goal_ids = {goal_id for goal_id, _, _ in tracking_goals_info}
    return [
        {'date': item['date'], 'goal_id': item['goal_id'], 'reaches': item['reaches']}
        for item in goals_fact
        if item['goal_id'] in tracking_goal_ids
    ]