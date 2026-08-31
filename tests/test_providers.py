"""Provider-level smoke tests (no network)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from email.message import Message
from email.utils import formatdate

import pytest

from coverart_cli.providers.base import CoverProvider, ProviderUnavailable
from coverart_cli.providers.lastfm import LastFmProvider
from coverart_cli.providers.musicbrainz import MusicBrainzProvider

from .image_fixtures import VALID_JPEG  # pyrefly: ignore [missing-import]


class DummyProvider(CoverProvider):
    name = "dummy"
    user_agent = "dummy/1.0"
    allowed_hosts = frozenset({"example.com"})

    def fetch(self, artist: str, album: str):
        return None


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.offset = 0
        self.url = "https://example.com/cover.jpg"

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.payload) - self.offset
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


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


@pytest.mark.parametrize(
    "mismatch",
    [
        {"artistName": "The Beatles", "collectionName": "Abbey Road"},
        {"artistName": "Pink Floyd", "collectionName": "Revolver"},
        {"artistName": "", "collectionName": "Revolver"},
        {"collectionName": "Revolver"},
    ],
)
def test_itunes_rejects_partial_or_missing_identity_matches(
    mismatch: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from coverart_cli.providers import ITunesProvider

    mismatch["artworkUrl100"] = "https://is1-ssl.mzstatic.com/image/100x100bb.jpg"
    payload = json.dumps({"results": [mismatch]}).encode()
    urls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> bytes:
        urls.append(url)
        return payload

    provider = ITunesProvider()
    monkeypatch.setattr(provider, "_http_get", fake_get)

    assert provider.fetch("The Beatles", "Revolver") is None
    assert len(urls) == 1


def test_itunes_skips_mismatch_then_accepts_full_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coverart_cli.providers import ITunesProvider

    payload = json.dumps(
        {
            "results": [
                {
                    "artistName": "The Beatles",
                    "collectionName": "Abbey Road",
                    "artworkUrl100": "https://is1-ssl.mzstatic.com/bad/100x100bb.jpg",
                },
                {
                    "artistName": "The Beatles",
                    "collectionName": "Revolver",
                    "artworkUrl100": "https://is1-ssl.mzstatic.com/good/100x100bb.jpg",
                },
            ]
        }
    ).encode()
    urls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> bytes:
        urls.append(url)
        return payload if len(urls) == 1 else VALID_JPEG

    provider = ITunesProvider()
    monkeypatch.setattr(provider, "_http_get", fake_get)

    result = provider.fetch("The Beatles", "Revolver")
    assert result is not None
    assert result.image_bytes == VALID_JPEG
    assert all("/bad/" not in url for url in urls)
    assert any("/good/" in url for url in urls)


@pytest.mark.parametrize(
    "mismatch",
    [
        {"artist": {"name": "The Beatles"}, "title": "Abbey Road"},
        {"artist": {"name": "Pink Floyd"}, "title": "Revolver"},
        {"artist": {}, "title": "Revolver"},
        {"title": "Revolver"},
    ],
)
def test_deezer_rejects_partial_or_missing_identity_matches(
    mismatch: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    from coverart_cli.providers import DeezerProvider

    mismatch["cover_xl"] = "https://cdn-images.dzcdn.net/images/cover/bad"
    payload = json.dumps({"data": [mismatch]}).encode()
    urls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> bytes:
        urls.append(url)
        return payload

    provider = DeezerProvider()
    monkeypatch.setattr(provider, "_http_get", fake_get)

    assert provider.fetch("The Beatles", "Revolver") is None
    assert len(urls) == 1


def test_deezer_skips_mismatch_then_accepts_full_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coverart_cli.providers import DeezerProvider

    payload = json.dumps(
        {
            "data": [
                {
                    "artist": {"name": "The Beatles"},
                    "title": "Abbey Road",
                    "cover_xl": "https://cdn-images.dzcdn.net/images/cover/bad",
                },
                {
                    "artist": {"name": "The Beatles"},
                    "title": "Revolver",
                    "cover_xl": "https://cdn-images.dzcdn.net/images/cover/good",
                },
            ]
        }
    ).encode()
    urls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> bytes:
        urls.append(url)
        return payload if len(urls) == 1 else VALID_JPEG

    provider = DeezerProvider()
    monkeypatch.setattr(provider, "_http_get", fake_get)

    result = provider.fetch("The Beatles", "Revolver")
    assert result is not None
    assert result.image_bytes == VALID_JPEG
    assert all("/bad" not in url for url in urls)
    assert any("/good" in url for url in urls)


@pytest.mark.parametrize(
    ("requested", "candidate"),
    [
        ("Queen", "Queens of the Stone Age"),
        ("Air", "Air Supply"),
        ("Live", "Live at Wembley"),
    ],
)
def test_catalogue_identity_rejects_free_substrings(requested: str, candidate: str) -> None:
    from coverart_cli.providers.base import _catalogue_text_matches

    assert not _catalogue_text_matches(requested, candidate)


@pytest.mark.parametrize(
    "payload",
    [
        b"null",
        b"[]",
        b'{"results": null}',
        b'{"results": [{"artistName": "Artist", "collectionName": "Album", "artworkUrl100": 7}]}',
    ],
)
def test_itunes_treats_schema_drift_as_a_miss(
    payload: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coverart_cli.providers import ITunesProvider

    provider = ITunesProvider()
    monkeypatch.setattr(provider, "_http_get", lambda _url, **_kwargs: payload)
    assert provider.fetch("Artist", "Album") is None


@pytest.mark.parametrize(
    "payload",
    [
        b"null",
        b"[]",
        b'{"data": null}',
        b'{"data": [{"artist": {"name": "Artist"}, "title": "Album", "cover_xl": 7}]}',
    ],
)
def test_deezer_treats_schema_drift_as_a_miss(
    payload: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coverart_cli.providers import DeezerProvider

    provider = DeezerProvider()
    monkeypatch.setattr(provider, "_http_get", lambda _url, **_kwargs: payload)
    assert provider.fetch("Artist", "Album") is None


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
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: FakeOpener(b"x" * 11))

    result = DummyProvider()._http_get("https://example.com/cover.jpg", max_bytes=10)
    assert result is None


def test_http_get_accepts_responses_at_size_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: FakeOpener(b"x" * 10))

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


@pytest.mark.parametrize(
    "payload",
    [b"null", b"[]", b'{"album": null}', b'{"album": {"image": null}}'],
)
def test_lastfm_treats_schema_drift_as_a_miss(
    payload: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = LastFmProvider("key")
    monkeypatch.setattr(provider, "_http_get", lambda _url, **_kwargs: payload)
    assert provider.fetch("Artist", "Album") is None


@pytest.mark.parametrize("error_code", [4, 8, 29, 999])
def test_lastfm_surfaces_explicit_error_payload(
    error_code: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = LastFmProvider("key")
    monkeypatch.setattr(
        provider,
        "_http_get",
        lambda _url, **_kwargs: json.dumps(
            {"error": error_code, "message": "untrusted provider detail"}
        ).encode(),
    )

    with pytest.raises(ProviderUnavailable, match=f"Last.fm API error {error_code}"):
        provider.fetch("Artist", "Album")


@pytest.mark.parametrize(
    "payload",
    [b"null", b"[]", b'{"release-groups": null}', b'{"release-groups": [null]}'],
)
def test_musicbrainz_treats_schema_drift_as_a_miss(
    payload: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = MusicBrainzProvider()
    monkeypatch.setattr(provider, "_http_get", lambda _url, **_kwargs: payload)
    monkeypatch.setattr(provider, "_respect_rate_limit", lambda: None)
    assert provider.fetch("Artist", "Album") is None


def test_catalogue_identity_preserves_exact_punctuation_only_names() -> None:
    from coverart_cli.providers.base import _catalogue_text_matches

    assert _catalogue_text_matches("!!!", "!!!")
    assert not _catalogue_text_matches("!!!", "???")


def test_http_get_honors_bounded_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    class RetryOpener:
        attempts = 0

        def open(self, request: urllib.request.Request, timeout: int) -> FakeResponse:
            self.attempts += 1
            if self.attempts == 1:
                headers = Message()
                headers["Retry-After"] = "999"
                raise urllib.error.HTTPError(
                    request.full_url,
                    429,
                    "rate limited",
                    headers,
                    None,
                )
            return FakeResponse(b"ok")

    opener = RetryOpener()
    sleeps: list[float] = []
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: opener)
    monkeypatch.setattr("coverart_cli.providers.base.time.sleep", sleeps.append)

    assert DummyProvider()._http_get("https://example.com/cover.jpg", retries=1) == b"ok"
    assert sleeps == [120.0]


def test_http_get_honors_retry_after_http_date(monkeypatch: pytest.MonkeyPatch) -> None:
    class RetryOpener:
        attempts = 0

        def open(self, request: urllib.request.Request, timeout: int) -> FakeResponse:
            self.attempts += 1
            if self.attempts == 1:
                headers = Message()
                headers["Retry-After"] = formatdate(60, usegmt=True)
                raise urllib.error.HTTPError(request.full_url, 429, "limited", headers, None)
            return FakeResponse(b"ok")

    sleeps: list[float] = []
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: RetryOpener())
    monkeypatch.setattr("coverart_cli.providers.base.time.time", lambda: 0.0)
    monkeypatch.setattr("coverart_cli.providers.base.time.sleep", sleeps.append)

    assert DummyProvider()._http_get("https://example.com/cover.jpg", retries=1) == b"ok"
    assert sleeps == [60.0]


def test_http_get_honors_retry_after_on_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RetryOpener:
        attempts = 0

        def open(self, request: urllib.request.Request, timeout: int) -> FakeResponse:
            self.attempts += 1
            if self.attempts == 1:
                headers = Message()
                headers["Retry-After"] = "60"
                raise urllib.error.HTTPError(request.full_url, 503, "down", headers, None)
            return FakeResponse(b"ok")

    opener = RetryOpener()
    sleeps: list[float] = []
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: opener)
    monkeypatch.setattr("coverart_cli.providers.base.time.sleep", sleeps.append)

    assert DummyProvider()._http_get("https://example.com/cover.jpg", retries=1) == b"ok"
    assert sleeps == [60.0]


def test_http_get_retries_connection_reset_during_body_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenResponse(FakeResponse):
        def read(self, size: int = -1) -> bytes:
            raise ConnectionResetError("reset")

    class RetryOpener:
        attempts = 0

        def open(self, request: urllib.request.Request, timeout: int) -> FakeResponse:
            self.attempts += 1
            return BrokenResponse(b"") if self.attempts == 1 else FakeResponse(b"ok")

    opener = RetryOpener()
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: opener)
    monkeypatch.setattr("coverart_cli.providers.base.time.sleep", lambda _delay: None)

    assert DummyProvider()._http_get("https://example.com/cover.jpg", retries=1) == b"ok"
    assert opener.attempts == 2


def test_musicbrainz_rate_limit_uses_monotonic_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = MusicBrainzProvider()
    ticks = iter([100.0, 100.2])
    sleeps: list[float] = []
    monkeypatch.setattr("coverart_cli.providers.musicbrainz.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("coverart_cli.providers.musicbrainz.time.sleep", sleeps.append)
    provider._last_request = 99.5

    provider._respect_rate_limit()

    assert sleeps == [pytest.approx(0.6)]
    assert provider._last_request == 100.2


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("offline"),
        urllib.error.HTTPError("https://example.com", 503, "down", Message(), None),
        urllib.error.HTTPError("https://example.com", 429, "limited", Message(), None),
    ],
)
def test_http_get_surfaces_exhausted_transient_failure(
    error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingOpener:
        def open(self, request: urllib.request.Request, timeout: int) -> FakeResponse:
            raise error

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: FailingOpener())

    with pytest.raises(ProviderUnavailable):
        DummyProvider()._http_get("https://example.com/cover.jpg", retries=0)


def test_http_get_keeps_not_found_distinct_from_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingOpener:
        def open(self, request: urllib.request.Request, timeout: int) -> FakeResponse:
            raise urllib.error.HTTPError(request.full_url, 404, "missing", Message(), None)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: MissingOpener())

    assert DummyProvider()._http_get("https://example.com/cover.jpg", retries=0) is None


@pytest.mark.parametrize("status", [401, 403])
def test_http_get_surfaces_authorization_failure(
    status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    class UnauthorizedOpener:
        def open(self, request: urllib.request.Request, timeout: int) -> FakeResponse:
            raise urllib.error.HTTPError(request.full_url, status, "unauthorized", Message(), None)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: UnauthorizedOpener())

    with pytest.raises(ProviderUnavailable, match=f"HTTP {status}"):
        DummyProvider()._http_get("https://example.com/cover.jpg", retries=0)


def test_itunes_rate_limiter_runs_for_every_search_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coverart_cli.providers import ITunesProvider

    class RetryOpener:
        attempts = 0

        def open(self, request: urllib.request.Request, timeout: int) -> FakeResponse:
            self.attempts += 1
            if self.attempts == 1:
                raise urllib.error.HTTPError(request.full_url, 503, "down", Message(), None)
            response = FakeResponse(b'{"results": []}')
            response.url = request.full_url
            return response

    limiter_calls: list[None] = []
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: RetryOpener())
    monkeypatch.setattr("coverart_cli.providers.base.time.sleep", lambda _delay: None)
    provider = ITunesProvider()
    monkeypatch.setattr(provider, "_respect_rate_limit", lambda: limiter_calls.append(None))

    assert provider.fetch("Artist", "Album") is None
    assert len(limiter_calls) == 2


def test_lastfm_rejects_mismatched_catalogue_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps(
        {
            "album": {
                "artist": "The Beatles",
                "name": "Abbey Road",
                "image": [{"size": "mega", "#text": "https://img.test/cover.jpg"}],
            }
        }
    ).encode()
    urls: list[str] = []
    provider = LastFmProvider("key")

    def fake_get(url: str, **kwargs: object) -> bytes:
        urls.append(url)
        return payload

    monkeypatch.setattr(provider, "_http_get", fake_get)

    assert provider.fetch("Pink Floyd", "The Wall") is None
    assert len(urls) == 1


def test_musicbrainz_rejects_mismatched_catalogue_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps(
        {
            "release-groups": [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "score": 100,
                    "title": "Abbey Road",
                    "artist-credit": [{"name": "The Beatles"}],
                }
            ]
        }
    ).encode()
    urls: list[str] = []
    provider = MusicBrainzProvider()
    monkeypatch.setattr(provider, "_respect_rate_limit", lambda: None)

    def fake_get(url: str, **kwargs: object) -> bytes:
        urls.append(url)
        return payload

    monkeypatch.setattr(provider, "_http_get", fake_get)

    assert provider.fetch("Pink Floyd", "The Wall") is None
    assert len(urls) == 1


def test_lastfm_accepts_exact_catalogue_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_url = "https://lastfm.freetls.fastly.net/cover.jpg"
    payload = json.dumps(
        {
            "album": {
                "artist": "Pink Floyd",
                "name": "The Wall",
                "image": [{"size": "mega", "#text": image_url}],
            }
        }
    ).encode()
    provider = LastFmProvider("key")
    monkeypatch.setattr(
        provider,
        "_http_get",
        lambda url, **_kwargs: VALID_JPEG if url == image_url else payload,
    )

    result = provider.fetch("Pink Floyd", "The Wall")
    assert result is not None
    assert result.image_bytes == VALID_JPEG


def test_musicbrainz_accepts_exact_catalogue_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps(
        {
            "release-groups": [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "score": "100",
                    "title": "The Wall",
                    "artist-credit": [{"name": "Pink Floyd"}],
                }
            ]
        }
    ).encode()
    provider = MusicBrainzProvider()
    monkeypatch.setattr(provider, "_respect_rate_limit", lambda: None)
    monkeypatch.setattr(
        provider,
        "_http_get",
        lambda url, **_kwargs: VALID_JPEG if "coverartarchive" in url else payload,
    )

    result = provider.fetch("Pink Floyd", "The Wall")
    assert result is not None
    assert result.image_bytes == VALID_JPEG
