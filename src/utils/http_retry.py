import time
from typing import Any, Dict, Iterable, Optional, Set
import os

import requests


DEFAULT_RETRYABLE_STATUS: Set[int] = {429, 500, 502, 503, 504}


def post_json_with_retry(
    url: str,
    payload: Dict[str, Any],
    timeout: int,
    max_retries: int = 3,
    backoff_factor: float = 1.5,
    retryable_status: Optional[Iterable[int]] = None,
) -> requests.Response:
    env_retry = os.getenv("LLMMUI_HTTP_MAX_RETRIES")
    if env_retry is not None and env_retry.strip() != "":
        try:
            max_retries = max(0, int(env_retry))
        except ValueError:
            pass

    status_set = set(retryable_status or DEFAULT_RETRYABLE_STATUS)
    last_exc: Optional[Exception] = None

    session = requests.Session()
    # Force local direct connection and ignore inherited proxy settings.
    session.trust_env = False

    for attempt in range(max_retries + 1):
        try:
            resp = session.post(url, json=payload, timeout=timeout, proxies={"http": None, "https": None})
            if resp.status_code in status_set:
                raise requests.HTTPError(
                    f"Retryable HTTP status {resp.status_code}",
                    response=resp,
                )
            resp.raise_for_status()
            return resp
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            last_exc = exc
            if attempt >= max_retries:
                raise
            sleep_seconds = backoff_factor ** attempt
            time.sleep(sleep_seconds)

    raise RuntimeError(f"Failed to POST {url}: {last_exc}")
