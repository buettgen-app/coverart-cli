"""Apple Music / iTunes Search API provider — no key required."""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse

from coverart_cli.providers.base import (
    CoverProvider,
    ProviderResult,
    _catalogue_text_matches,
    _default_user_agent,
)
from coverart_cli.tagging import MIN_COVER_BYTES

log = logging.getLogger(__name__)

ITUNES_SEARCH = "https://itunes.apple.com/search"
ITUNES_MIN_DELAY = 3.1


class ITunesProvider(CoverProvider):
    """Search Apple's public iTunes catalogue. Returns the largest available artwork."""

    name = "itunes"
    allowed_hosts = frozenset({"itunes.apple.com", ".mzstatic.com"})

    def __init__(self, user_agent: str | None = None) -> None:
        self.user_agent = user_agent or _default_user_agent()
        self._last_request = 0.0
        self._rate_lock = threading.Lock()

    def fetch(self, artist: str, album: str) -> ProviderResult | None:
        params = {
            "term": f"{artist} {album}",
            "entity": "album",
            "limit": "5",
            "media": "music",
        }
        raw = self._http_get(
            ITUNES_SEARCH + "?" + urllib.parse.urlencode(params),
            before_attempt=self._respect_rate_limit,
        )
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None
        results = data.get("results")
        if not isinstance(results, list):
            return None

        for hit in results:
            if not isinstance(hit, dict):
                continue
            artist_match = _catalogue_text_matches(artist, hit.get("artistName"))
            album_match = _catalogue_text_matches(album, hit.get("collectionName"))
            if not (artist_match and album_match):
                continue
            url = hit.get("artworkUrl100")
            if not isinstance(url, str) or not url:
                continue
            # iTunes returns 100x100; ask for 1000x1000 by swapping the suffix.
            hi_res = url.replace("100x100bb", "1000x1000bb").replace("100x100", "1000x1000")
            img = self._http_get(hi_res, timeout=25)
            if img and len(img) >= MIN_COVER_BYTES:
                return ProviderResult(image_bytes=img, source=self.name, image_url=hi_res)
        return None

    def _respect_rate_limit(self) -> None:
        """Stay below the catalogue's documented approximate 20 calls/minute limit."""
        with self._rate_lock:
            elapsed = time.monotonic() - self._last_request
            if elapsed < ITUNES_MIN_DELAY:
                time.sleep(ITUNES_MIN_DELAY - elapsed)
            self._last_request = time.monotonic()
