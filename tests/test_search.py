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
    assert search._passes_length_filter(120, search.LENGTH_SHORT)
    assert not search._passes_length_filter(200, search.LENGTH_SHORT)
    assert search._passes_length_filter(200, search.LENGTH_MEDIUM)
    assert search._passes_length_filter(300, search.LENGTH_LONG)
    # "הכל" ואורך לא ידוע לא מסננים כלום
    assert search._passes_length_filter(1, search.ALL)
    assert search._passes_length_filter(0, search.LENGTH_LONG)


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
