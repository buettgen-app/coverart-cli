"""Last.fm album.getinfo provider."""

from __future__ import annotations

import json
import logging
import urllib.parse
from collections.abc import Sequence

from coverart_cli.providers.base import (
    CoverProvider,
    ProviderResult,
    ProviderUnavailable,
    _catalogue_text_matches,
    _default_user_agent,
)
from coverart_cli.tagging import MIN_COVER_BYTES

log = logging.getLogger(__name__)

LASTFM_API = "https://ws.audioscrobbler.com/2.0/"
# Last.fm sometimes returns a star-graphic placeholder URL — recognize and reject.
PLACEHOLDER_HASHES = frozenset(
    {
        "2a96cbd8b46e442fc41c2b86b821562f",  # "2a96cbd8" known placeholder
    }
)


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
        if not isinstance(data, dict):
            return None
        error_code = data.get("error")
        if error_code is not None:
            try:
                parsed_error = int(error_code)
            except (TypeError, ValueError):
                parsed_error = "unknown"
            raise ProviderUnavailable(f"Last.fm API error {parsed_error}")
        album_data = data.get("album")
        if not isinstance(album_data, dict):
            return None
        returned_artist = album_data.get("artist")
        if isinstance(returned_artist, dict):
            returned_artist = returned_artist.get("name")
        if not (
            _catalogue_text_matches(artist, returned_artist)
            and _catalogue_text_matches(album, album_data.get("name"))
        ):
            return None
        images = album_data.get("image")
        if not isinstance(images, list):
            return None
        image_url = self._best_image(images)
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
    def _best_image(images: Sequence[object]) -> str | None:
        for size in ("mega", "extralarge", "large"):
            for img in images:
                if not isinstance(img, dict):
                    continue
                if img.get("size") != size:
                    continue
                url = img.get("#text", "")
                if not isinstance(url, str) or not url:
                    continue
                if any(p in url for p in PLACEHOLDER_HASHES):
                    continue
                return url
        return None
