from db.db_config import DB_CONFIG
from fetch.fetch_goals_fact import fetch_goals_fact
from extract.extract_counters import extract_counters
from transform.filter_goals_fact import filter_goals_fact
from monitoring.find_broken_goals import find_broken_goals
from save.save_goals_fact_to_db import save_goals_fact_to_db
from extract.extract_tracking_goals_info import extract_tracking_goals_info
from extract.extract_agencies_info import extract_agencies_info
from fetch.fetch_counters import fetch_counters
from save.save_counters_to_db import save_counters_to_db
from fetch.fetch_goals_info import fetch_goals_info
from save.save_goals_info_to_db import save_goals_to_db


# Весь цикл работы мониторинга
# agencies = extract_agencies_info(DB_CONFIG)
# counters = fetch_counters(agencies)
# save_counters_to_db(DB_CONFIG, counters)
# goals_info = fetch_goals_info(counters)
# save_goals_to_db(DB_CONFIG, goals_info)
counters_for_facts = extract_counters(DB_CONFIG)
all_goals_fact = fetch_goals_fact(counters_for_facts)
tracking_goals_info = extract_tracking_goals_info(DB_CONFIG)
filtered_goals_fact = filter_goals_fact(all_goals_fact, tracking_goals_info)
save_goals_fact_to_db(DB_CONFIG, filtered_goals_fact)
find_broken_goals(DB_CONFIG)