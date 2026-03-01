import time
from typing import Any, Dict, Iterable, Optional, Set

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
    status_set = set(retryable_status or DEFAULT_RETRYABLE_STATUS)
    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
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
