"""Provider interface — fetch cover art for a given artist + album."""

from __future__ import annotations

import http.client
import io
import logging
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

MAX_HTTP_RESPONSE_BYTES = 20 * 1024 * 1024


def _safe_url_for_log(url: str) -> str:
    """Return a URL safe for logs (scheme + host + path only)."""
    try:
        parsed = urllib.parse.urlsplit(url)
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except Exception:
        return "<invalid-url>"


log = logging.getLogger(__name__)


def _is_allowed_https_url(url: str, allowed_hosts: frozenset[str]) -> bool:
    """Accept HTTPS URLs only when their hostname matches an explicit allowlist."""
    try:
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return False
    if parsed.scheme != "https" or not host:
        return False
    return any(
        host == pattern.lstrip(".") or (pattern.startswith(".") and host.endswith(pattern))
        for pattern in allowed_hosts
    )


class _RestrictedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Apply the same host boundary to every redirect before following it."""

    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        self.allowed_hosts = allowed_hosts
        super().__init__()

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_allowed_https_url(newurl, self.allowed_hosts):
            raise urllib.error.HTTPError(newurl, 403, "redirect host is not allowed", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


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


class ProviderUnavailable(RuntimeError):
    """Raised after a transient provider/network failure exhausts its retries."""


def _retry_after_seconds(headers: object, default: float) -> float:
    """Parse bounded Retry-After delta seconds or an HTTP date."""
    value = headers.get("Retry-After") if hasattr(headers, "get") else None
    if value is None:
        return default
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            seconds = parsedate_to_datetime(str(value)).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            return default
    return max(default, min(120.0, max(0.0, seconds)))


class CoverProvider(ABC):
    """Abstract provider — subclasses implement fetch()."""

    name: str = "base"
    user_agent: str = "coverart-cli"  # subclasses override in __init__
    allowed_hosts: frozenset[str] = frozenset()

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
        before_attempt: Callable[[], None] | None = None,
    ) -> bytes | None:
        """HTTP GET with retry on transient failures (5xx, timeout)."""
        if not _is_allowed_https_url(url, self.allowed_hosts):
            log.debug("blocked URL outside provider host policy: %s", _safe_url_for_log(url))
            return None

        last_err: Exception | None = None
        opener = urllib.request.build_opener(_RestrictedRedirectHandler(self.allowed_hosts))
        for attempt in range(retries + 1):
            if before_attempt is not None:
                before_attempt()
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            try:
                with opener.open(req, timeout=timeout) as r:
                    final_url = getattr(r, "url", url)
                    if not _is_allowed_https_url(final_url, self.allowed_hosts):
                        log.debug("blocked final URL outside provider host policy")
                        return None
                    deadline = time.monotonic() + timeout
                    headers = getattr(r, "headers", None)
                    content_length = headers.get("Content-Length") if headers else None
                    with suppress(TypeError, ValueError):
                        if content_length is not None and int(content_length) > max_bytes:
                            return None
                    buffer = io.BytesIO()
                    received = 0
                    while received <= max_bytes:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("HTTP response exceeded the wall-clock deadline")
                        chunk = r.read(min(64 * 1024, max_bytes + 1 - received))
                        if not chunk:
                            return buffer.getvalue()
                        buffer.write(chunk)
                        received += len(chunk)
                    log.debug("%s response too large", _safe_url_for_log(url))
                    return None
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                    log.debug(
                        "%s transient %s, retry %d/%d",
                        _safe_url_for_log(url),
                        e.code,
                        attempt + 1,
                        retries,
                    )
                    delay = backoff * (2**attempt)
                    if e.code in {429, 503}:
                        delay = _retry_after_seconds(e.headers, delay)
                    time.sleep(delay)
                    last_err = e
                    continue
                log.debug("%s HTTP %s", _safe_url_for_log(url), e.code)
                if e.code in (429, 500, 502, 503, 504):
                    raise ProviderUnavailable(f"HTTP {e.code} after retries") from e
                if e.code in (401, 403):
                    raise ProviderUnavailable(f"HTTP {e.code} authorization failure") from e
                return None
            except (
                urllib.error.URLError,
                TimeoutError,
                http.client.HTTPException,
                OSError,
            ) as e:
                if attempt < retries:
                    time.sleep(backoff * (2**attempt))
                    last_err = e
                    continue
                log.debug("%s network error: %s", _safe_url_for_log(url), e)
                raise ProviderUnavailable("network failure after retries") from e
        if last_err:
            log.debug("%s exhausted retries: %s", _safe_url_for_log(url), last_err)
        return None


def _catalogue_text_matches(requested: str, candidate: object) -> bool:
    """Return whether a non-empty catalogue field matches the requested value."""
    if not isinstance(candidate, str):
        return False

    def normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        tokens = ["".join(ch for ch in token if ch.isalnum()) for token in normalized.split()]
        tokens = [token for token in tokens if token]
        if tokens[:1] == ["the"]:
            tokens = tokens[1:]
        return " ".join(tokens)

    requested_normalized = normalize(requested)
    candidate_normalized = normalize(candidate)
    if requested_normalized or candidate_normalized:
        return bool(requested_normalized) and requested_normalized == candidate_normalized

    def exact_fallback(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())

    requested_exact = exact_fallback(requested)
    return bool(requested_exact) and requested_exact == exact_fallback(candidate)
