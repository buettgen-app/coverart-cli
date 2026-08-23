"""Provider interface — fetch cover art for a given artist + album."""
from __future__ import annotations

import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass

MAX_HTTP_RESPONSE_BYTES = 20 * 1024 * 1024


def _safe_url_for_log(url: str) -> str:
    """Return a URL safe for logs (scheme + host + path only)."""
    try:
        parsed = urllib.parse.urlsplit(url)
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except Exception:
        return "<invalid-url>"

log = logging.getLogger(__name__)


def _default_user_agent() -> str:
    """Build a sensible default UA string from the current package version."""
    # Local import to avoid a circular dep at module import time.
    from coverart_cli import __version__

    return f"coverart-cli/{__version__} (+https://github.com/buettgen-app/coverart-cli)"


@dataclass(frozen=True)
class ProviderResult:
    """Cover art bytes + provenance info."""

    image_bytes: bytes
    source: str
    image_url: str


class CoverProvider(ABC):
    """Abstract provider — subclasses implement fetch()."""

    name: str = "base"
    user_agent: str = "coverart-cli"  # subclasses override in __init__

    @abstractmethod
    def fetch(self, artist: str, album: str) -> ProviderResult | None:
        """Return cover bytes for the album, or None if not found."""

    def _http_get(
        self,
        url: str,
        *,
        timeout: int = 15,
        retries: int = 2,
        backoff: float = 1.0,
        max_bytes: int = MAX_HTTP_RESPONSE_BYTES,
    ) -> bytes | None:
        """HTTP GET with retry on transient failures (5xx, timeout)."""
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    body = r.read(max_bytes + 1)
                    if len(body) > max_bytes:
                        log.debug("%s response too large", _safe_url_for_log(url))
                        return None
                    return body
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                    log.debug(
                        "%s transient %s, retry %d/%d",
                        _safe_url_for_log(url), e.code, attempt + 1, retries,
                    )
                    time.sleep(backoff * (2**attempt))
                    last_err = e
                    continue
                log.debug("%s HTTP %s", _safe_url_for_log(url), e.code)
                return None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < retries:
                    time.sleep(backoff * (2**attempt))
                    last_err = e
                    continue
                log.debug("%s network error: %s", _safe_url_for_log(url), e)
                return None
        if last_err:
            log.debug("%s exhausted retries: %s", _safe_url_for_log(url), last_err)
        return None
