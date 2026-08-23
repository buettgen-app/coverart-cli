"""Last.fm album.getinfo provider."""
from __future__ import annotations

import json
import logging
import urllib.parse

from coverart_cli.providers.base import CoverProvider, ProviderResult, _default_user_agent
from coverart_cli.tagging import MIN_COVER_BYTES

log = logging.getLogger(__name__)

LASTFM_API = "https://ws.audioscrobbler.com/2.0/"
# Last.fm sometimes returns a star-graphic placeholder URL — recognize and reject.
PLACEHOLDER_HASHES = frozenset({
    "2a96cbd8b46e442fc41c2b86b821562f",  # "2a96cbd8" known placeholder
})


class LastFmProvider(CoverProvider):
    name = "lastfm"
    allowed_hosts = frozenset({"ws.audioscrobbler.com", ".lastfm.freetls.fastly.net"})

    def __init__(self, api_key: str, user_agent: str | None = None) -> None:
        if not api_key:
            raise ValueError("Last.fm API key is required")
        self.api_key = api_key
        self.user_agent = user_agent or _default_user_agent()

    def fetch(self, artist: str, album: str) -> ProviderResult | None:
        url = self._build_info_url(artist, album)
        raw = self._http_get(url)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.debug("lastfm: invalid JSON for %s / %s", artist, album)
            return None
        if "album" not in data:
            return None
        image_url = self._best_image(data["album"].get("image", []))
        if not image_url:
            return None
        img = self._http_get(image_url, timeout=25)
        if not img or len(img) < MIN_COVER_BYTES:
            return None
        return ProviderResult(image_bytes=img, source=self.name, image_url=image_url)

    def _build_info_url(self, artist: str, album: str) -> str:
        params = {
            "method": "album.getinfo",
            "api_key": self.api_key,
            "artist": artist,
            "album": album,
            "format": "json",
            "autocorrect": "1",
        }
        return LASTFM_API + "?" + urllib.parse.urlencode(params)

    @staticmethod
    def _best_image(images: list[dict]) -> str | None:
        for size in ("mega", "extralarge", "large"):
            for img in images:
                if img.get("size") != size:
                    continue
                url = img.get("#text", "")
                if not url:
                    continue
                if any(p in url for p in PLACEHOLDER_HASHES):
                    continue
                return url
        return None
