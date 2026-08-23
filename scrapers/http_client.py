"""
Reusable HTTP client for the scraping pipeline.

Design decisions:
- requests.Session for connection pooling and default headers.
- urllib3 Retry adapter: retries on connection errors and 5xx responses,
  but NOT on 4xx (those are caller errors, not transient faults).
- Hard timeout of 20s (connect + read) to prevent hanging indefinitely.
- No authentication / cookie injection — we only hit public pages.
- robots.txt compliance is handled by not hitting disallowed paths
  (verified manually per source — see source module comments).
- Crawl-delay is enforced in the source, not here, to keep concerns separate.
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

USER_AGENT = (
    "ResearchConnectAI/0.1 "
    "(academic research project; +https://github.com/FuricBond/Research-Connect-AI)"
)
DEFAULT_TIMEOUT = (10, 20)   # (connect_timeout, read_timeout) in seconds
MAX_RETRIES = 3
BACKOFF_FACTOR = 1.5          # waits: 0s, 1.5s, 3s between retries

# Status codes that are worth retrying (transient server errors only)
RETRY_STATUS_CODES = {500, 502, 503, 504}


def _build_session() -> requests.Session:
    """Build a requests.Session with retry adapter and default headers."""
    session = requests.Session()

    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=RETRY_STATUS_CODES,
        allowed_methods={"GET", "HEAD"},
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
    )
    return session


class HttpClient:
    """
    Thin HTTP client wrapper for the scraping pipeline.

    Usage:
        client = HttpClient()
        html = client.get("https://example.com/page")

    The caller is responsible for enforcing crawl-delay between requests.
    This client handles transport-level concerns only.
    """

    def __init__(self) -> None:
        self._session = _build_session()

    def get(
        self,
        url: str,
        *,
        timeout: tuple[int, int] = DEFAULT_TIMEOUT,
        params: dict | None = None,
    ) -> str:
        """
        Perform a GET request and return the response body as text.

        Raises:
            requests.HTTPError: On non-2xx responses (after exhausting retries).
            requests.RequestException: On network/timeout errors.
        """
        parsed = urlparse(url)
        logger.debug("GET %s://%s%s", parsed.scheme, parsed.netloc, parsed.path)

        try:
            response = self._session.get(
                url,
                params=params,
                timeout=timeout,
                allow_redirects=True,
            )
        except requests.Timeout:
            logger.error("Timeout fetching %s (timeout=%s)", url, timeout)
            raise
        except requests.ConnectionError as exc:
            logger.error("Connection error fetching %s: %s", url, exc)
            raise
        except requests.RequestException as exc:
            logger.error("Request error fetching %s: %s", url, exc)
            raise

        if not response.ok:
            logger.warning(
                "HTTP %d fetching %s — will not retry 4xx errors",
                response.status_code,
                url,
            )
            response.raise_for_status()

        logger.info("Fetched %s [%d] (%d bytes)", url, response.status_code, len(response.content))
        return response.text

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def fetch_with_delay(
    client: HttpClient,
    url: str,
    crawl_delay: float,
    *,
    params: dict | None = None,
) -> str:
    """
    Fetch a URL and sleep for `crawl_delay` seconds afterwards.

    This keeps the caller's loop simple while ensuring the site is not hammered.
    """
    html = client.get(url, params=params)
    if crawl_delay > 0:
        logger.debug("Sleeping %.1fs (crawl_delay)", crawl_delay)
        time.sleep(crawl_delay)
    return html
