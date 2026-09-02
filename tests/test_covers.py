import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import covers


def make(artist, track, uid="1", preview="http://p", duration=200, album=""):
    return {
        "source": "iTunes", "uid": uid, "artist": artist, "track": track, "album": album,
        "duration_sec": duration, "preview_url": preview, "artwork": "", "genre": "",
    }


def test_find_covers_uses_musicbrainz_when_shs_unavailable(monkeypatch):
    monkeypatch.setattr(covers, "shs_search_work", lambda *a, **k: None)
    monkeypatch.setattr(covers, "musicbrainz_versions", lambda *a, **k: [
        {"artist": "2WEI", "track": "Zombie", "year": "2018", "source_db": "MusicBrainz"},
    ])
    monkeypatch.setattr(covers, "_enrich_one", lambda v, c: make(v["artist"], v["track"]))

    results, source, _ = covers.find_covers("Zombie", "The Cranberries")
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

    results, source, _ = covers.find_covers("Zombie")
    assert source == "SecondHandSongs"
    assert not called  # לא נופלים לאחור כשהמקור הראשי החזיר תוצאות


def test_find_covers_excludes_the_original_performer(monkeypatch):
    monkeypatch.setattr(covers, "shs_search_work", lambda *a, **k: {"uri": "http://x"})
    monkeypatch.setattr(covers, "shs_list_versions", lambda *a, **k: [
        {"artist": "The Cranberries", "track": "Zombie", "source_db": "SecondHandSongs"},
        {"artist": "2WEI", "track": "Zombie", "source_db": "SecondHandSongs"},
    ])
    monkeypatch.setattr(covers, "_enrich_one", lambda v, c: make(v["artist"], v["track"]))

    results, _, _ = covers.find_covers("Zombie", "The Cranberries")
    assert [t["artist"] for t in results] == ["2WEI"]


def test_find_covers_returns_empty_when_both_sources_fail(monkeypatch):
    monkeypatch.setattr(covers, "shs_search_work", lambda *a, **k: None)
    monkeypatch.setattr(covers, "musicbrainz_versions", lambda *a, **k: [])
    assert covers.find_covers("Nonexistent Song") == ([], "", None)


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


# ---------- רגרסיה: חיפוש "Sweet Dreams" החזיר קאנטרי מ-1960 ----------

def test_work_query_is_not_an_exact_phrase(monkeypatch):
    """'Sweet Dreams' חייב להגיע גם ל-'Sweet Dreams (Are Made of This)'."""
    captured = {}

    def fake_get(path, params, client=None):
        captured["params"] = params
        return {"works": [
            {"id": "w1", "title": "Sweet Dreams", "disambiguation": "1955 country song"},
            {"id": "w2", "title": "Sweet Dreams (Are Made of This)", "disambiguation": "Eurythmics"},
        ]}

    monkeypatch.setattr(covers, "_mb_get", fake_get)
    results = covers.musicbrainz_work_candidates("Sweet Dreams")
    assert '"Sweet Dreams"' not in captured["params"]["query"]
    assert {c["id"] for c in results} == {"w1", "w2"}


def test_explicit_work_id_skips_auto_resolution(monkeypatch):
    called = []
    monkeypatch.setattr(covers, "musicbrainz_work_candidates",
                        lambda *a, **k: called.append(1) or [])
    monkeypatch.setattr(covers, "_mb_get", lambda *a, **k: {"recordings": [
        {"title": "Sweet Dreams", "artist-credit": [{"name": "Eurythmics"}]},
    ]})
    versions = covers.musicbrainz_versions("Sweet Dreams", work_id="w2")
    assert not called  # לא מזהים יצירה כשכבר נבחרה אחת
    assert versions[0]["artist"] == "Eurythmics"


def test_shs_is_skipped_when_a_work_was_chosen(monkeypatch):
    shs_calls = []
    monkeypatch.setattr(covers, "shs_search_work", lambda *a, **k: shs_calls.append(1) or None)
    monkeypatch.setattr(covers, "musicbrainz_versions", lambda *a, **k: [
        {"artist": "Eurythmics", "track": "Sweet Dreams (Are Made of This)"},
    ])
    monkeypatch.setattr(covers, "_enrich_one", lambda v, c: make(v["artist"], v["track"]))
    results, source, _ = covers.find_covers("Sweet Dreams", work_id="w2")
    assert not shs_calls
    assert source == "MusicBrainz"
    assert results[0]["artist"] == "Eurythmics"


def test_duplicate_store_matches_get_unique_uids(monkeypatch):
    """הקריסה: StreamlitDuplicateElementKey על chk_itunes-322093141."""
    monkeypatch.setattr(covers, "shs_search_work", lambda *a, **k: {"uri": "http://x"})
    monkeypatch.setattr(covers, "shs_list_versions", lambda *a, **k: [
        {"artist": "Patsy Cline", "track": "Sweet Dreams"},
        {"artist": "Patsy Cline & Friends", "track": "Sweet Dreams"},
    ])
    # שתי הגרסאות נפתרות לאותה תוצאה בחנות, ולכן לאותו uid
    monkeypatch.setattr(covers, "_enrich_one",
                        lambda v, c: {**make(v["artist"], v["track"]), "uid": "itunes-322093141"})
    results, _, _ = covers.find_covers("Sweet Dreams")
    uids = [t["uid"] for t in results]
    assert len(uids) == len(set(uids)), f"uid כפול: {uids}"


# ---------- סינון "רק לטריילרים" ----------

def _covers_with(versions, monkeypatch, enriched=None):
    monkeypatch.setattr(covers, "shs_search_work", lambda *a, **k: {"uri": "http://x"})
    monkeypatch.setattr(covers, "shs_list_versions", lambda *a, **k: versions)
    monkeypatch.setattr(covers, "_enrich_one",
                        enriched or (lambda v, c: make(v["artist"], v["track"])))




# ---------- כפתור "רק גרסאות טריילר אפיות" ----------

def _epic_pool():
    return [
        make("2WEI", "Summertime (Epic Trailer Version)", uid="a"),
        make("Lana Del Rey", "Summertime (Imanbek Remix)", uid="b"),
        make("SL", "Summertime", uid="c"),
        make("Someone", "Summertime", uid="d", album="Dark Cinematic Covers"),
    ]


def test_epic_search_keeps_only_self_declared_epic_versions(monkeypatch):
    """הבעיה שדווחה: החיפוש החזיר בעיקר קאברים נעימים."""
    monkeypatch.setattr(covers.search_module, "search_covers", lambda *a, **k: _epic_pool())
    results, source = covers.find_epic_versions("Summertime")
    assert {t["artist"] for t in results} == {"2WEI", "Someone"}
    assert source == "חיפוש בחנויות"


def test_epic_search_excludes_the_original_performer(monkeypatch):
    pool = _epic_pool() + [make("Eurythmics", "Summertime (Epic Version)", uid="e")]
    monkeypatch.setattr(covers.search_module, "search_covers", lambda *a, **k: pool)
    results, _ = covers.find_epic_versions("Summertime", "Eurythmics")
    assert "Eurythmics" not in {t["artist"] for t in results}


def test_epic_search_can_come_back_empty(monkeypatch):
    monkeypatch.setattr(covers.search_module, "search_covers",
                        lambda *a, **k: [make("SL", "Summertime")])
    results, _ = covers.find_epic_versions("Summertime")
    assert results == []


def test_reference_version_must_be_playable():
    """Helen Jepson מ-1935 בלי preview היא בסיס השוואה חסר תועלת."""
    versions = [
        {"artist": "Helen Jepson", "track": "Summertime", "year": "1935", "preview_url": ""},
        {"artist": "Ella Fitzgerald", "track": "Summertime", "year": "1957",
         "preview_url": "http://p"},
    ]
    assert covers.pick_original(versions)["artist"] == "Ella Fitzgerald"


def test_unplayable_original_is_used_when_nothing_else_exists():
    versions = [{"artist": "Helen Jepson", "track": "Summertime", "year": "1935",
                 "preview_url": ""}]
    assert covers.pick_original(versions)["artist"] == "Helen Jepson"
