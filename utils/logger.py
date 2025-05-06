import os
import logging

# Получаем путь к корневой папке проекта (относительно этого файла)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "project.log")

# Создаём папку logs, если её нет
os.makedirs(LOG_DIR, exist_ok=True)

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()  # Лог также будет выводиться в консоль
    ]
)

logger = logging.getLogger(__name__)