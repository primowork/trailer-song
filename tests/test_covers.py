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


def test_declared_epic_versions_come_first(monkeypatch):
    """הכותרת מכניסה, אבל אינה מוציאה."""
    monkeypatch.setattr(covers.search_module, "search_covers", lambda *a, **k: _epic_pool())
    results, source = covers.find_epic_versions("Summertime")
    declared = [t["artist"] for t in results if t["trailer_indicator"]]
    assert set(declared) == {"2WEI", "Someone"}
    assert [t["artist"] for t in results[:2]] == declared
    assert source == "חיפוש בחנויות"


def test_a_remix_is_not_dropped_for_lacking_the_word_epic(monkeypatch):
    """רמיקס יכול להיות גרסה ענקית; הגודל מחליט, לא הכותרת."""
    monkeypatch.setattr(covers.search_module, "search_covers", lambda *a, **k: _epic_pool())
    results, _ = covers.find_epic_versions("Summertime")
    remix = [t for t in results if t["artist"] == "Lana Del Rey"]
    assert remix, "הרמיקס נמחק מהתוצאות"
    assert remix[0]["trailer_indicator"] is False


def test_epic_search_excludes_the_original_performer(monkeypatch):
    pool = _epic_pool() + [make("Eurythmics", "Summertime (Epic Version)", uid="e")]
    monkeypatch.setattr(covers.search_module, "search_covers", lambda *a, **k: pool)
    results, _ = covers.find_epic_versions("Summertime", "Eurythmics")
    assert "Eurythmics" not in {t["artist"] for t in results}


def test_nothing_declared_still_returns_candidates(monkeypatch):
    monkeypatch.setattr(covers.search_module, "search_covers",
                        lambda *a, **k: [make("SL", "Summertime")])
    results, _ = covers.find_epic_versions("Summertime")
    assert [t["artist"] for t in results] == ["SL"]
    assert results[0]["trailer_indicator"] is False


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


# ---------- מיזוג קטלוג + חנויות ----------

def test_find_all_covers_merges_and_tags_both_sources(monkeypatch):
    catalog = [make("MB Cover", "Zombie", uid="c1")]
    store = [make("Store Cover", "Zombie (Epic Trailer Version)", uid="s1")]
    monkeypatch.setattr(covers, "find_covers",
                        lambda title, artist="", limit=80, work_id="": (catalog, "MusicBrainz", None))
    monkeypatch.setattr(covers, "find_epic_versions",
                        lambda title, artist="", limit=60, filters=None, prefer_new=False, min_year=0:
                            (store, "חיפוש בחנויות"))

    results, source, original = covers.find_all_covers("Zombie")
    assert {t["artist"] for t in results} == {"MB Cover", "Store Cover"}
    assert {t["catalog_source"] for t in results} == {"MusicBrainz", "חיפוש בחנויות"}
    assert "MusicBrainz" in source and "חיפוש בחנויות" in source


def test_find_all_covers_dedupes_the_same_track_from_both_sources(monkeypatch):
    same_from_catalog = make("2WEI", "Zombie", uid="db-2wei-zombie")
    same_from_store = make("2WEI", "Zombie", uid="itunes-x")
    monkeypatch.setattr(covers, "find_covers",
                        lambda title, artist="", limit=80, work_id="": ([same_from_catalog], "MusicBrainz", None))
    monkeypatch.setattr(covers, "find_epic_versions",
                        lambda title, artist="", limit=60, filters=None, prefer_new=False, min_year=0:
                            ([same_from_store], "חיפוש בחנויות"))

    results, _, _ = covers.find_all_covers("Zombie")
    assert len(results) == 1


def test_find_all_covers_when_one_source_is_empty(monkeypatch):
    monkeypatch.setattr(covers, "find_covers",
                        lambda title, artist="", limit=80, work_id="": ([], "", None))
    store = [make("Store Cover", "Zombie (Epic)", uid="s1")]
    monkeypatch.setattr(covers, "find_epic_versions",
                        lambda title, artist="", limit=60, filters=None, prefer_new=False, min_year=0:
                            (store, "חיפוש בחנויות"))

    results, source, _ = covers.find_all_covers("Zombie")
    assert [t["artist"] for t in results] == ["Store Cover"]
    assert source == "חיפוש בחנויות"


# ---------- חיפוש לפי אמן ----------

def _song(artist, track, uid="x"):
    return {"source": "iTunes", "uid": f"itunes-{uid}", "artist": artist,
            "track": track, "album": "", "duration_sec": 200,
            "preview_url": "http://p", "artwork": "", "genre": "",
            "release_date": "", "year": "2020"}


CATALOG = (
    # "Yellow" חוזר על ארבעה אוספים, "Sparks" על אחד: כך נראה להיט בקטלוג
    [_song("Coldplay", "Yellow", f"y{i}") for i in range(4)]
    + [_song("Coldplay", "Clocks", f"c{i}") for i in range(3)]
    + [_song("Coldplay", "Sparks", "s1")]
    + [_song("Some Tribute Band", "Yellow", "t1")]
)


def test_artist_top_titles_ranks_by_appearances(monkeypatch):
    monkeypatch.setattr(covers.search_module, "itunes_search",
                        lambda *a, **k: [dict(item) for item in CATALOG])
    titles = covers.artist_top_titles("Coldplay", limit=3)
    assert titles[:2] == ["Yellow", "Clocks"]
    # שיר של אמן אחר אינו נספר לאמן שביקשנו
    assert len(titles) == 3


def test_artist_top_titles_without_a_name_makes_no_call(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("לא אמורה להיות קריאה")
    monkeypatch.setattr(covers.search_module, "itunes_search", boom)
    assert covers.artist_top_titles("  ") == []


def test_find_artist_covers_tags_and_dedupes(monkeypatch):
    monkeypatch.setattr(covers.search_module, "itunes_search",
                        lambda *a, **k: [dict(item) for item in CATALOG])
    monkeypatch.setattr(covers, "artist_top_titles", lambda artist, limit=8: ["Yellow", "Clocks"])

    # אותו קאבר חוזר משני השירים: חייב להופיע פעם אחת, אחרת ה-uid כפול והעמוד נופל
    shared = _song("Epic Covers", "Yellow (Epic Trailer Version)", "shared")
    per_title = {
        "Yellow": [shared, _song("Trailer Music", "Yellow (Cinematic)", "a")],
        "Clocks": [dict(shared)],
    }
    monkeypatch.setattr(covers, "find_epic_versions",
                        lambda title, artist, limit=12, filters=None, prefer_new=False, min_year=0:
                            ([dict(t) for t in per_title[title]], "x"))

    results, source, titles = covers.find_artist_covers("Coldplay")
    assert titles == ["Yellow", "Clocks"]
    assert source
    assert len({t["uid"] for t in results}) == len(results) == 2
    assert {t["origin_track"] for t in results} <= {"Yellow", "Clocks"}


def test_find_artist_covers_without_titles_returns_empty(monkeypatch):
    monkeypatch.setattr(covers, "artist_top_titles", lambda artist, limit=8: [])
    assert covers.find_artist_covers("Nobody") == ([], "", [])


# ---------- "עוד כמו זה" ובורר היצירות ----------

def test_famous_recording_picks_the_most_repeated_performer(monkeypatch):
    catalog = ([_song("Rihanna", "Umbrella", f"r{i}") for i in range(5)]
               + [_song("Karaoke Band", "Umbrella", "k1")]
               + [_song("Someone", "Umbrella (Epic Trailer Version)", "e1")])
    monkeypatch.setattr(covers.search_module, "itunes_search",
                        lambda *a, **k: [dict(i) for i in catalog])
    hit = covers.famous_recording("umbrella")
    assert hit["artist"] == "Rihanna"


def test_famous_recording_without_a_match_is_none(monkeypatch):
    monkeypatch.setattr(covers.search_module, "itunes_search", lambda *a, **k: [])
    assert covers.famous_recording("nothing here") is None
    assert covers.famous_recording("  ") is None


def test_more_covers_of_uses_the_origin_title(monkeypatch):
    seen = {}

    def fake(title, artist="", limit=40, filters=None, prefer_new=False, min_year=0):
        seen["title"] = title
        return [_song("Other", "Yellow (Cinematic)", "o1"),
                _song("Self", "Yellow (Epic)", "self")], "x"

    monkeypatch.setattr(covers, "find_epic_versions", fake)
    monkeypatch.setattr(covers, "find_covers", lambda *a, **k: ([], "", None))
    track = _song("Self", "Yellow (Epic Trailer Version)", "self")
    results, _ = covers.more_covers_of(track)
    # הכותרת מנוקה לשם השיר המקורי, והטראק עצמו אינו חוזר כהצעה לעצמו
    assert seen["title"] == "Yellow"
    assert [t["uid"] for t in results] == ["itunes-o1"]
    assert results[0]["origin_track"] == "Yellow"


def test_more_covers_of_prefers_the_declared_origin(monkeypatch):
    seen = {}
    monkeypatch.setattr(covers, "find_epic_versions",
                        lambda title, artist="", limit=40, filters=None, prefer_new=False, min_year=0:
                            (seen.update(title=title) or [], "x"))
    monkeypatch.setattr(covers, "find_covers", lambda *a, **k: ([], "", None))
    covers.more_covers_of({**_song("A", "Something Else", "z"), "origin_track": "Clocks"})
    assert seen["title"] == "Clocks"


def test_more_like_style_without_genre_or_artist_is_empty():
    assert covers.more_like_style({"uid": "x", "artist": "", "genre": ""}) == ([], "")


def test_more_like_style_searches_genre_and_artist(monkeypatch):
    terms = []

    def fake_search(term, **kwargs):
        terms.append(term)
        return [_song("Neighbour", f"Track {term}", term)]

    monkeypatch.setattr(covers.search_module, "search_covers", fake_search)
    track = {**_song("2WEI", "Survivor", "src"), "genre": "Soundtrack"}
    results, source = covers.more_like_style(track)
    assert terms == ["Soundtrack", "2WEI"]
    assert source and len(results) == 2
    assert "itunes-src" not in {t["uid"] for t in results}
