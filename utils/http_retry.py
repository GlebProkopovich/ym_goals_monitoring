"""Повторные HTTP-запросы с экспоненциальной паузой."""

import time

import requests

from utils.logger import logger
from utils.metrika_api_counter import increment_metrika_api_request, is_metrika_api_url

DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_SEC = 2.0
RETRY_HTTP_STATUS = {429, 500, 502, 503, 504}


def request_with_retry(method, url, *, retries=DEFAULT_RETRIES, backoff_sec=DEFAULT_BACKOFF_SEC, **kwargs):
    """
    Выполняет HTTP-запрос с повторами при сетевых ошибках и временных кодах ответа.
    Запросы к api-metrika.yandex.net учитываются в суточном счётчике (utils/metrika_api_counter).

    Raises:
        requests.exceptions.RequestException: если все попытки исчерпаны.
    """
    last_error = None
    timeout = kwargs.pop("timeout", 30)
    track_metrika = is_metrika_api_url(url)

    for attempt in range(1, retries + 1):
        try:
            if track_metrika:
                increment_metrika_api_request()

            response = requests.request(method, url, timeout=timeout, **kwargs)

            if response.status_code in RETRY_HTTP_STATUS and attempt < retries:
                wait = backoff_sec * (2 ** (attempt - 1))
                logger.warning(
                    f"HTTP {response.status_code} для {url}, повтор {attempt}/{retries} через {wait:.1f} с"
                )
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt < retries:
                wait = backoff_sec * (2 ** (attempt - 1))
                logger.warning(
                    f"Ошибка запроса {url}: {exc}. Повтор {attempt}/{retries} через {wait:.1f} с"
                )
                time.sleep(wait)
            else:
                logger.error(f"Запрос {url} не удался после {retries} попыток: {exc}")

    raise last_error
