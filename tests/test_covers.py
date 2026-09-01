import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import covers


def make(artist, track, uid="1", preview="http://p", duration=200):
    return {
        "source": "iTunes", "uid": uid, "artist": artist, "track": track, "album": "",
        "duration_sec": duration, "preview_url": preview, "artwork": "", "genre": "",
    }


def test_is_epic_performer():
    assert covers.is_epic_performer("2WEI")
    assert covers.is_epic_performer("2WEI feat. Edda Hayes")
    assert covers.is_epic_performer("Tommee Profitt")
    assert not covers.is_epic_performer("The Cranberries")


def test_find_covers_uses_musicbrainz_when_shs_unavailable(monkeypatch):
    monkeypatch.setattr(covers, "shs_search_work", lambda *a, **k: None)
    monkeypatch.setattr(covers, "musicbrainz_versions", lambda *a, **k: [
        {"artist": "2WEI", "track": "Zombie", "year": "2018", "source_db": "MusicBrainz"},
    ])
    monkeypatch.setattr(covers, "_enrich_one", lambda v, c: make(v["artist"], v["track"]))

    results, source = covers.find_covers("Zombie", "The Cranberries")
    assert source == "MusicBrainz"
    assert [t["artist"] for t in results] == ["2WEI"]


def test_find_covers_prefers_secondhandsongs(monkeypatch):
    monkeypatch.setattr(covers, "shs_search_work", lambda *a, **k: {"uri": "http://x"})
    monkeypatch.setattr(covers, "shs_list_versions", lambda *a, **k: [
        {"artist": "2WEI", "track": "Zombie", "source_db": "SecondHandSongs"},
    ])
    called = []
    monkeypatch.setattr(covers, "musicbrainz_versions",
                        lambda *a, **k: called.append(1) or [])
    monkeypatch.setattr(covers, "_enrich_one", lambda v, c: make(v["artist"], v["track"]))

    results, source = covers.find_covers("Zombie")
    assert source == "SecondHandSongs"
    assert not called  # לא נופלים לאחור כשהמקור הראשי החזיר תוצאות


def test_find_covers_excludes_the_original_performer(monkeypatch):
    monkeypatch.setattr(covers, "shs_search_work", lambda *a, **k: {"uri": "http://x"})
    monkeypatch.setattr(covers, "shs_list_versions", lambda *a, **k: [
        {"artist": "The Cranberries", "track": "Zombie", "source_db": "SecondHandSongs"},
        {"artist": "2WEI", "track": "Zombie", "source_db": "SecondHandSongs"},
    ])
    monkeypatch.setattr(covers, "_enrich_one", lambda v, c: make(v["artist"], v["track"]))

    results, _ = covers.find_covers("Zombie", "The Cranberries")
    assert [t["artist"] for t in results] == ["2WEI"]


def test_find_covers_epic_only_filter(monkeypatch):
    monkeypatch.setattr(covers, "shs_search_work", lambda *a, **k: {"uri": "http://x"})
    monkeypatch.setattr(covers, "shs_list_versions", lambda *a, **k: [
        {"artist": "Some Local Band", "track": "Zombie", "source_db": "SecondHandSongs"},
        {"artist": "Tommee Profitt", "track": "Zombie", "source_db": "SecondHandSongs"},
    ])
    monkeypatch.setattr(covers, "_enrich_one", lambda v, c: make(v["artist"], v["track"]))

    results, _ = covers.find_covers("Zombie", epic_only=True)
    assert [t["artist"] for t in results] == ["Tommee Profitt"]


def test_epic_performers_rank_above_others(monkeypatch):
    monkeypatch.setattr(covers, "shs_search_work", lambda *a, **k: {"uri": "http://x"})
    monkeypatch.setattr(covers, "shs_list_versions", lambda *a, **k: [
        {"artist": "Some Local Band", "track": "Zombie", "source_db": "SecondHandSongs"},
        {"artist": "2WEI", "track": "Zombie", "source_db": "SecondHandSongs"},
    ])
    monkeypatch.setattr(covers, "_enrich_one", lambda v, c: make(v["artist"], v["track"]))

    results, _ = covers.find_covers("Zombie")
    assert results[0]["artist"] == "2WEI"
    assert results[0]["is_epic_performer"] is True


def test_find_covers_returns_empty_when_both_sources_fail(monkeypatch):
    monkeypatch.setattr(covers, "shs_search_work", lambda *a, **k: None)
    monkeypatch.setattr(covers, "musicbrainz_versions", lambda *a, **k: [])
    assert covers.find_covers("Nonexistent Song") == ([], "")


def test_shs_search_work_handles_error_status(monkeypatch):
    class FakeResponse:
        status_code = 503
        def json(self):
            raise AssertionError("לא אמור להיקרא על סטטוס שגיאה")

    class FakeClient:
        def get(self, *a, **k):
            return FakeResponse()

    assert covers.shs_search_work("Zombie", client=FakeClient()) is None


def test_enrich_falls_back_when_track_not_in_stores(monkeypatch):
    monkeypatch.setattr(covers.search_module, "itunes_search", lambda *a, **k: [])
    monkeypatch.setattr(covers.search_module, "deezer_search", lambda *a, **k: [])
    version = {"artist": "Obscure Artist", "track": "Zombie", "source_db": "SecondHandSongs"}
    enriched = covers._enrich_one(version, None)
    assert enriched["artist"] == "Obscure Artist"
    assert enriched["preview_url"] == ""
