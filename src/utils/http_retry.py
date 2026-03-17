import time
from typing import Any, Dict, Iterable, Optional, Set
import os
from urllib.parse import urlparse
import ipaddress

import requests


DEFAULT_RETRYABLE_STATUS: Set[int] = {429, 500, 502, 503, 504}


def _is_loopback_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").strip().lower()
    except Exception:
        return False
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


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
    # Loopback endpoints should bypass proxy to avoid local proxy hijack.
    bypass_proxy = _is_loopback_url(url)
    if bypass_proxy:
        session.trust_env = False

    for attempt in range(max_retries + 1):
        try:
            request_kwargs = {"json": payload, "timeout": timeout}
            if bypass_proxy:
                request_kwargs["proxies"] = {"http": None, "https": None}
            resp = session.post(url, **request_kwargs)
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
