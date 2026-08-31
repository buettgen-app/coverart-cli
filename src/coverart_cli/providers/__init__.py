"""Cover art providers — Last.fm, iTunes, Deezer, MusicBrainz / Cover Art Archive."""

from coverart_cli.providers.base import CoverProvider, ProviderResult
from coverart_cli.providers.deezer import DeezerProvider
from coverart_cli.providers.itunes import ITunesProvider
from coverart_cli.providers.lastfm import LastFmProvider
from coverart_cli.providers.musicbrainz import MusicBrainzProvider

__all__ = [
    "CoverProvider",
    "ProviderResult",
    "LastFmProvider",
    "ITunesProvider",
    "DeezerProvider",
    "MusicBrainzProvider",
]
