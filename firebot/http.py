"""Shared HTTP session: connection pooling + retries for idempotent GETs.

All source fetches go through one module-level ``requests.Session`` so TLS
connections are reused across polls, and transient failures (connection resets,
429/5xx) are retried with backoff instead of killing the source for a whole cycle.

Only GETs are retried. Discord webhook POSTs must NOT be auto-retried here — a
retried POST whose first attempt actually landed would double-post; ``discord.py``
keeps its own explicit 429 handling and uses this session for pooling only.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_retry = Retry(
    total=3,
    backoff_factor=1.0,  # 0s, 2s, 4s between attempts
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=("GET",),
    raise_on_status=False,  # let callers' raise_for_status() surface the final error
)

session = requests.Session()
_adapter = HTTPAdapter(max_retries=_retry)
session.mount("https://", _adapter)
session.mount("http://", _adapter)


def get(url: str, **kwargs) -> requests.Response:
    """GET through the shared retrying session."""
    return session.get(url, **kwargs)
