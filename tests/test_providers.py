"""Provider-level smoke tests (no network)."""
from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from coverart_cli.providers.base import CoverProvider
from coverart_cli.providers.lastfm import LastFmProvider
from coverart_cli.providers.musicbrainz import MusicBrainzProvider


class DummyProvider(CoverProvider):
    name = "dummy"
    user_agent = "dummy/1.0"
    allowed_hosts = frozenset({"example.com"})

    def fetch(self, artist: str, album: str):
        return None


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.url = "https://example.com/cover.jpg"

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            return self.payload
        return self.payload[:size]


def test_lastfm_requires_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        LastFmProvider(api_key="")


def test_lastfm_best_image_picks_largest() -> None:
    images = [
        {"size": "small", "#text": "http://example.com/s.jpg"},
        {"size": "large", "#text": "http://example.com/l.jpg"},
        {"size": "extralarge", "#text": "http://example.com/xl.jpg"},
        {"size": "mega", "#text": "http://example.com/mega.jpg"},
    ]
    assert LastFmProvider._best_image(images) == "http://example.com/mega.jpg"


def test_lastfm_best_image_skips_placeholder() -> None:
    placeholder = "https://lastfm.freetls.fastly.net/i/u/2a96cbd8b46e442fc41c2b86b821562f.png"
    images = [{"size": "mega", "#text": placeholder}]
    assert LastFmProvider._best_image(images) is None


def test_lastfm_best_image_empty() -> None:
    assert LastFmProvider._best_image([]) is None
    assert LastFmProvider._best_image([{"size": "small", "#text": ""}]) is None


def test_musicbrainz_escape_strips_lucene_special_chars() -> None:
    assert MusicBrainzProvider._escape('Some "Album" (Deluxe)') == "Some  Album   Deluxe"
    assert MusicBrainzProvider._escape("Foo [Disc 1]") == "Foo  Disc 1"


def test_itunes_provider_instantiable() -> None:
    from coverart_cli.providers import ITunesProvider

    p = ITunesProvider()  # default
    assert p.user_agent
    p2 = ITunesProvider(user_agent="myua/1.0")  # explicit UA also works (regression)
    assert p2.user_agent == "myua/1.0"


def test_deezer_provider_instantiable() -> None:
    from coverart_cli.providers import DeezerProvider

    p = DeezerProvider()
    assert p.user_agent
    p2 = DeezerProvider(user_agent="myua/1.0")
    assert p2.user_agent == "myua/1.0"


def test_deezer_escape_strips_quotes() -> None:
    from coverart_cli.providers import DeezerProvider

    assert DeezerProvider._escape('"Foo" bar') == "Foo  bar"


def test_safe_url_for_log_strips_api_key() -> None:
    from coverart_cli.providers.base import _safe_url_for_log

    url = "https://ws.audioscrobbler.com/2.0/?method=album.getinfo&api_key=SECRET123"
    sanitized = _safe_url_for_log(url)
    assert "SECRET123" not in sanitized
    assert "api_key" not in sanitized
    assert sanitized == "https://ws.audioscrobbler.com/2.0/"


def test_safe_url_for_log_strips_entire_query() -> None:
    from coverart_cli.providers.base import _safe_url_for_log

    url = "https://itunes.apple.com/search?term=Pink+Floyd&entity=album"
    sanitized = _safe_url_for_log(url)
    assert "?" not in sanitized
    assert "term" not in sanitized
    assert sanitized == "https://itunes.apple.com/search"


def test_safe_url_for_log_keeps_path() -> None:
    from coverart_cli.providers.base import _safe_url_for_log

    url = "https://coverartarchive.org/release-group/abcd-1234/front-1000"
    sanitized = _safe_url_for_log(url)
    assert sanitized == url  # no query → unchanged


def test_safe_url_for_log_handles_garbage() -> None:
    from coverart_cli.providers.base import _safe_url_for_log

    # Anything urlsplit can parse should round-trip safely; nothing should crash.
    assert "<invalid-url>" not in _safe_url_for_log("https://example.com")
    assert _safe_url_for_log("") == ""


class FakeOpener:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def open(self, request: urllib.request.Request, timeout: int) -> FakeResponse:
        return FakeResponse(self.payload)


def test_http_get_rejects_responses_over_size_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *handlers: FakeOpener(b"x" * 11)
    )

    result = DummyProvider()._http_get("https://example.com/cover.jpg", max_bytes=10)
    assert result is None


def test_http_get_accepts_responses_at_size_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *handlers: FakeOpener(b"x" * 10)
    )

    result = DummyProvider()._http_get("https://example.com/cover.jpg", max_bytes=10)
    assert result == b"x" * 10


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/cover.jpg",
        "https://example.com.evil.test/cover.jpg",
        "https://127.0.0.1/cover.jpg",
    ],
)
def test_http_get_blocks_urls_outside_provider_policy(url: str) -> None:
    assert DummyProvider()._http_get(url) is None


def test_redirect_handler_blocks_disallowed_host() -> None:
    from coverart_cli.providers.base import _RestrictedRedirectHandler

    handler = _RestrictedRedirectHandler(frozenset({"example.com"}))
    request = urllib.request.Request("https://example.com/start")
    with pytest.raises(urllib.error.HTTPError, match="redirect host is not allowed"):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://127.0.0.1/private",
        )
