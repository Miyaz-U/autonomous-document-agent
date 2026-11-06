import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import RATE_LIMIT_PER_HOUR

WINDOW_SECONDS = 3600
GLOBAL_LIMIT_PER_HOUR = 40  # protects the shared free-tier LLM quota

_ip_hits = defaultdict(deque)
_global_hits = deque()


def _client_ip(request: Request) -> str:
    # Behind Render's proxy, the real IP is the first entry of X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune(hits: deque, now: float) -> None:
    while hits and now - hits[0] > WINDOW_SECONDS:
        hits.popleft()


def check_rate_limit(request: Request) -> None:
    """Raise HTTP 429 if this visitor (or the whole service) is over its hourly limit."""
    now = time.time()
    ip_hits = _ip_hits[_client_ip(request)]
    _prune(ip_hits, now)
    _prune(_global_hits, now)

    if len(ip_hits) >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=f"Demo limit reached ({RATE_LIMIT_PER_HOUR} documents per hour per visitor). Please try again later.",
        )
    if len(_global_hits) >= GLOBAL_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="The demo is busy right now. Please try again in a little while.",
        )

    ip_hits.append(now)
    _global_hits.append(now)