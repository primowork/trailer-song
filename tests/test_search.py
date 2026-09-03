import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import search


def make(artist, track, source="iTunes", uid="1", album="", preview="http://p", duration=200, genre=""):
    return {
        "source": source, "uid": uid, "artist": artist, "track": track, "album": album,
        "duration_sec": duration, "preview_url": preview, "artwork": "", "genre": genre,
    }


def test_clean_artist_removes_features_and_brackets():
    assert search.clean_artist_name("2WEI feat. Edda Hayes") == "2WEI"
    assert search.clean_artist_name("Tommee Profitt (Official)") == "Tommee Profitt"


def test_clean_track_keeps_titles_containing_from():
    # רגרסיה: "from" חתך כותרות לגיטימיות בגרסה הקודמת
    assert search.clean_track_title("Coming From Nowhere") == "Coming From Nowhere"
    assert search.clean_track_title("Survivor (Epic Trailer Version)") == "Survivor"


def test_track_key_ignores_album_and_punctuation():
    a = search.track_key("2WEI feat. Edda Hayes", "Survivor (Epic Trailer Version)")
    b = search.track_key("2WEI", "Survivor!")
    assert a == b


def test_build_queries_includes_raw_and_variants():
    queries = search.build_queries("victory", {"style": "Epic Orchestral", "tempo": search.ALL})
    assert queries[0] == "victory"          # השאילתה הגולמית נשמרת
    assert "victory trailer cover" in queries
    assert "victory Epic Orchestral" in queries
    assert len(queries) == len(set(queries))


def test_build_queries_empty_input():
    assert search.build_queries("   ") == []


def test_dedupe_collapses_same_song_across_albums_and_sources():
    tracks = [
        make("2WEI", "Survivor", uid="a", album="Single"),
        make("2WEI", "Survivor (Epic Trailer Version)", uid="b", album="Compilation"),
        make("2WEI feat. Edda Hayes", "Survivor", source="Deezer", uid="c"),
        make("Hidden Citizens", "Paint It Black", uid="d"),
    ]
    for t in tracks:
        t["score"] = 50
    assert len(search.dedupe(tracks)) == 2


def test_dedupe_prefers_entry_with_preview():
    no_preview = make("2WEI", "Survivor", uid="a", preview="")
    no_preview["score"] = 90
    with_preview = make("2WEI", "Survivor", uid="b")
    with_preview["score"] = 10
    assert search.dedupe([no_preview, with_preview])[0]["uid"] == "b"


def test_score_ranks_epic_cover_above_unrelated():
    epic = make("2WEI", "Victory (Epic Trailer Cover)", album="Cinematic Covers", genre="Soundtrack")
    unrelated = make("Random Band", "Victory Lap", genre="Pop")
    assert search.score_track(epic, "victory") > search.score_track(unrelated, "victory")


def test_score_penalizes_missing_preview():
    with_preview = make("2WEI", "Victory")
    without = make("2WEI", "Victory", preview="")
    assert search.score_track(with_preview, "victory") > search.score_track(without, "victory")


def test_length_filter_boundaries():
    assert search.passes_length_filter(120, search.LENGTH_SHORT)
    assert not search.passes_length_filter(200, search.LENGTH_SHORT)
    assert search.passes_length_filter(200, search.LENGTH_MEDIUM)
    assert search.passes_length_filter(300, search.LENGTH_LONG)
    # "הכל" ואורך לא ידוע לא מסננים כלום
    assert search.passes_length_filter(1, search.ALL)
    assert search.passes_length_filter(0, search.LENGTH_LONG)


def test_search_covers_excludes_seen_keys(monkeypatch):
    pool = [make("2WEI", "Survivor", uid="a"), make("Hidden Citizens", "Paint It Black", uid="b")]
    monkeypatch.setattr(search, "itunes_search", lambda *a, **k: list(pool))
    monkeypatch.setattr(search, "deezer_search", lambda *a, **k: [])

    everything = search.search_covers("survivor", include_seeds=False)
    assert {t["artist"] for t in everything} == {"2WEI", "Hidden Citizens"}

    excluded = search.search_covers(
        "survivor", exclude_keys={search.track_key("2WEI", "Survivor")}, include_seeds=False
    )
    assert {t["artist"] for t in excluded} == {"Hidden Citizens"}


def test_search_covers_survives_failing_source(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(search, "itunes_search", boom)
    monkeypatch.setattr(search, "deezer_search", lambda *a, **k: [make("2WEI", "Survivor")])
    # מקור שנופל לא אמור להפיל את החיפוש כולו — התוצאות מהמקור התקין נשמרות
    results = search.search_covers("survivor", include_seeds=False)
    assert [t["artist"] for t in results] == ["2WEI"]


def test_normalize_itunes_skips_incomplete():
    assert search._normalize_itunes({"artistName": "", "trackName": "X"}) is None
    assert search._normalize_itunes({"artistName": "A", "trackName": "B", "trackTimeMillis": 200000})["duration_sec"] == 200


# ---------- טריות, אמן מקור, ז'אנרים ----------

def test_freshness_decays_over_five_years():
    assert search.freshness_bonus({"year": "2026"}, 2026) == 25
    assert search.freshness_bonus({"year": "2024"}, 2026) == 15
    assert search.freshness_bonus({"year": "2021"}, 2026) == 0
    assert search.freshness_bonus({"year": ""}, 2026) == 0


def test_new_and_good_outranks_old_and_equally_good():
    """הבקשה: כל מה שחדש עם ציון גבוה מקבל קדימות."""
    new = make("A", "Victory", uid="n")
    new["year"] = str(search._dt.date.today().year)
    old = make("B", "Victory", uid="o")
    old["year"] = "2005"
    assert (search.score_track(new, "Victory", prefer_new=True)
            > search.score_track(old, "Victory", prefer_new=True))


def test_freshness_is_off_by_default():
    fresh = make("A", "Victory")
    fresh["year"] = str(search._dt.date.today().year)
    assert search.score_track(fresh, "Victory") == search.score_track(
        {**fresh, "year": "2005"}, "Victory")


def test_origin_artist_adds_cover_queries():
    queries = search.build_queries("Zombie", None, "The Cranberries")
    assert "The Cranberries cover" in queries
    assert "Zombie The Cranberries cover" in queries


def test_origin_artist_is_optional():
    assert search.build_queries("Zombie") == search.build_queries("Zombie", None, "")


def test_min_year_filters_old_releases(monkeypatch):
    recent = make("A", "Victory", uid="a")
    recent["year"] = "2025"
    ancient = make("B", "Victory", uid="b")
    ancient["year"] = "1999"
    monkeypatch.setattr(search, "itunes_search", lambda *a, **k: [recent, ancient])
    monkeypatch.setattr(search, "deezer_search", lambda *a, **k: [])
    results = search.search_covers("Victory", include_seeds=False, min_year=2020)
    assert [t["artist"] for t in results] == ["A"]


def test_tracks_without_a_year_survive_the_recency_filter(monkeypatch):
    """שנה לא ידועה אינה סיבה למחוק תוצאה."""
    undated = make("A", "Victory")
    monkeypatch.setattr(search, "itunes_search", lambda *a, **k: [undated])
    monkeypatch.setattr(search, "deezer_search", lambda *a, **k: [])
    assert search.search_covers("Victory", include_seeds=False, min_year=2020)


def test_itunes_normalization_carries_the_release_year():
    track = search._normalize_itunes({
        "artistName": "A", "trackName": "B", "releaseDate": "2024-03-15T12:00:00Z"})
    assert track["year"] == "2024"
    assert track["release_date"] == "2024-03-15"


def test_style_list_is_substantially_wider():
    assert len(search.STYLES) >= 20
    assert len(set(search.STYLES)) == len(search.STYLES)


# ---------- שכבת ה-HTTP: כישלון אינו "אין תוצאות" ----------

def test_get_json_retries_transient_failures(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status):
            self.status_code = status

        def json(self):
            return {"ok": True}

    def fake_get(url, **kwargs):
        calls.append(url)
        return Response(200 if len(calls) == 3 else 503)

    monkeypatch.setattr(search.httpx, "get", fake_get)
    monkeypatch.setattr(search.time, "sleep", lambda seconds: None)
    search.reset_errors()

    assert search.get_json("http://store/x") == {"ok": True}
    assert len(calls) == 3
    assert search.last_errors() == []


def test_get_json_gives_up_and_records_the_reason(monkeypatch):
    monkeypatch.setattr(search.httpx, "get",
                        lambda url, **kwargs: (_ for _ in ()).throw(OSError("boom")))
    monkeypatch.setattr(search.time, "sleep", lambda seconds: None)
    search.reset_errors()

    assert search.get_json("http://itunes.apple.com/search") is None
    errors = search.last_errors()
    assert len(errors) == 1 and "itunes.apple.com" in errors[0] and "boom" in errors[0]


def test_get_json_does_not_retry_a_permanent_status(monkeypatch):
    calls = []

    class Response:
        status_code = 404

        def json(self):
            return {}

    monkeypatch.setattr(search.httpx, "get",
                        lambda url, **kwargs: calls.append(url) or Response())
    monkeypatch.setattr(search.time, "sleep", lambda seconds: None)
    search.reset_errors()

    assert search.get_json("http://store/x") is None
    assert len(calls) == 1


def test_a_failed_store_lookup_is_not_an_empty_result(monkeypatch):
    """iTunes שנפל מחזיר [] כמו חיפוש ריק — ההבדל נשמר ב-last_errors."""
    monkeypatch.setattr(search, "get_json", lambda *a, **k: None)
    search.reset_errors()
    search._record_error("itunes.apple.com — HTTP 503")
    assert search.itunes_search("anything") == []
    assert search.last_errors()
