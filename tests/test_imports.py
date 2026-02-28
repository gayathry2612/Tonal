"""
Smoke tests — verify every public module can be imported without error.

These catch typos, missing __init__ exports, and broken dependencies early,
before any logic tests run.  No QApplication / display needed.
"""


def test_import_library():
    from tonal.core import library  # noqa: F401


def test_import_player():
    from tonal.core import player  # noqa: F401


def test_import_format_duration():
    from tonal.core.library import format_duration, format_ms
    assert callable(format_duration)
    assert callable(format_ms)


def test_import_supported_extensions():
    from tonal.core.library import SUPPORTED_EXTENSIONS
    assert isinstance(SUPPORTED_EXTENSIONS, set)
    assert len(SUPPORTED_EXTENSIONS) > 0


def test_import_get_album_art_bytes():
    from tonal.core.library import get_album_art_bytes
    assert callable(get_album_art_bytes)


def test_import_library_class():
    from tonal.core.library import Library
    assert Library is not None


def test_import_player_class():
    from tonal.core.player import Player
    assert Player is not None
