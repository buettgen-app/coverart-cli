"""Atheris target for report escaping and URL log redaction boundaries."""

from __future__ import annotations

import sys
import urllib.parse

import atheris  # type: ignore[missing-import]

with atheris.instrument_imports():  # pyrefly: ignore [missing-attribute]
    from coverart_cli.providers.base import _safe_url_for_log
    from coverart_cli.report import AlbumEntry, build_report


def TestOneInput(data: bytes) -> None:  # noqa: N802 - Atheris convention
    provider = atheris.FuzzedDataProvider(data)  # pyrefly: ignore [missing-attribute]
    value = provider.ConsumeUnicodeNoSurrogates(512)

    safe_url = _safe_url_for_log(value)
    parsed = urllib.parse.urlsplit(safe_url)
    if parsed.query or parsed.fragment:
        raise AssertionError("log-safe URLs must not retain query strings or fragments")

    entry = AlbumEntry(
        artist=value,
        album=provider.ConsumeUnicodeNoSurrogates(256),
        path="ignored",
        has_cover=provider.ConsumeBool(),
        source=provider.ConsumeUnicodeNoSurrogates(32),
        file_count=provider.ConsumeIntInRange(0, 100_000),
        cover_data_uri=None,
    )
    html = build_report(
        [entry],
        library_path=provider.ConsumeUnicodeNoSurrogates(256),
        template='<script type="application/json">__REPORT_DATA__</script>',
    )
    if html.count("</script>") != 1:
        raise AssertionError("report data escaped its application/json script container")


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
