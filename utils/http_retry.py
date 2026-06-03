"""Повторные HTTP-запросы с фиксированной паузой между попытками."""

import time

import requests

from utils.logger import logger
from utils.metrika_api_counter import increment_metrika_api_request, is_metrika_api_url

# Всего до 4 запросов: первая попытка + ещё 3 при любой ошибке
DEFAULT_RETRIES = 4
RETRY_PAUSE_SEC = 10.0
MAX_ERROR_BODY_LOG_LEN = 2000


def format_response_error_body(response, max_len=MAX_ERROR_BODY_LOG_LEN):
    """Текст ошибки из тела ответа (JSON Метрики или сырой текст)."""
    if response is None:
        return ""

    try:
        data = response.json()
        if isinstance(data, dict):
            parts = []
            if data.get("message"):
                parts.append(str(data["message"]))
            errors = data.get("errors")
            if isinstance(errors, list):
                for err in errors[:10]:
                    if isinstance(err, dict):
                        msg = err.get("message") or err.get("text") or err.get("error_type")
                        if msg:
                            parts.append(str(msg))
                    elif err:
                        parts.append(str(err))
            text = "; ".join(parts) if parts else str(data)
        else:
            text = str(data)
    except ValueError:
        text = (response.text or "").strip()

    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def _format_request_context(request_context):
    """Человекочитаемый контекст запроса (без repr всего dict в одну строку)."""
    if not request_context:
        return ""

    lines = []
    url = request_context.get("url")
    if url:
        lines.append(f"url: {url}")
    params = request_context.get("params")
    if isinstance(params, dict):
        for key, value in params.items():
            lines.append(f"  {key}: {value}")
    elif params:
        lines.append(str(params))
    return "\n".join(lines)


def format_request_exception_detail(exc, *, request_context=None):
    """Текст для лога/алерта: блоки разделены пустой строкой."""
    sections = [str(exc)]
    response = getattr(exc, "response", None)
    if response is not None:
        sections.append(f"HTTP {response.status_code}")
        body = format_response_error_body(response)
        if body:
            sections.append(f"ответ API: {body}")
    context_text = _format_request_context(request_context)
    if context_text:
        sections.append(f"контекст:\n{context_text}")
    return "\n\n".join(sections)


def _log_http_failure(url, response, request_kwargs, *, attempt, max_attempts, will_retry):
    body = format_response_error_body(response)
    params = request_kwargs.get("params")
    lines = [
        f"HTTP {response.status_code} — {url}",
    ]
    if params:
        lines.append(f"параметры: {params}")
    if body:
        lines.append(f"ответ API: {body}")
    if will_retry:
        lines.append(f"повтор {attempt}/{max_attempts}")
    message = " | ".join(lines)
    if will_retry:
        logger.warning(message)
    else:
        logger.error(message)


def request_with_retry(
    method,
    url,
    *,
    retries=DEFAULT_RETRIES,
    backoff_sec=RETRY_PAUSE_SEC,
    **kwargs,
):
    """
    Выполняет HTTP-запрос. При ошибке (сеть или HTTP >= 400) — до retries попыток всего,
    между неудачными попытками пауза backoff_sec (по умолчанию 10 с).
    Запросы к api-metrika.yandex.net учитываются в суточном счётчике.

    Raises:
        requests.exceptions.RequestException: если все попытки исчерпаны.
    """
    last_error = None
    timeout = kwargs.pop("timeout", 30)
    track_metrika = is_metrika_api_url(url)
    max_attempts = retries

    for attempt in range(1, max_attempts + 1):
        try:
            if track_metrika:
                increment_metrika_api_request()

            response = requests.request(method, url, timeout=timeout, **kwargs)

            if response.status_code >= 400:
                will_retry = attempt < max_attempts
                _log_http_failure(
                    url,
                    response,
                    kwargs,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    will_retry=will_retry,
                )

                if will_retry:
                    logger.warning(
                        f"Пауза {backoff_sec:.0f} с перед повтором запроса {url}"
                    )
                    time.sleep(backoff_sec)
                    continue

                response.raise_for_status()

            return response

        except requests.exceptions.RequestException as exc:
            last_error = exc
            detail = format_request_exception_detail(
                exc,
                request_context=kwargs.get("params"),
            )

            if attempt < max_attempts:
                logger.warning(
                    f"Ошибка запроса {url}: {detail}. "
                    f"Повтор {attempt}/{max_attempts} через {backoff_sec:.0f} с"
                )
                time.sleep(backoff_sec)
            else:
                logger.error(
                    f"Запрос {url} не удался после {max_attempts} попыток: {detail}"
                )

    raise last_error
