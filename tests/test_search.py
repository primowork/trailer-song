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
    pool = [make("2WEI", "Survivor", uid="a"), make("Hidden Citizens", "Survivor (Epic Cover)", uid="b")]
    monkeypatch.setattr(search, "itunes_search", lambda *a, **k: list(pool))
    monkeypatch.setattr(search, "deezer_search", lambda *a, **k: [])

    everything = search.search_covers("survivor", include_seeds=False)
    assert {t["artist"] for t in everything} == {"2WEI", "Hidden Citizens"}

    excluded = search.search_covers(
        "survivor", exclude_keys={search.track_key("2WEI", "Survivor")}, include_seeds=False
    )
    assert {t["artist"] for t in excluded} == {"Hidden Citizens"}


def test_relevance_penalizes_a_different_song_that_shares_two_words():
    """'At Long Last, Love' הוא שיר אחר לגמרי, לא קאבר של 'At Last'."""
    unrelated = make("Danny Elfman", "At Long Last, Love")
    legit_cover = make("Etta James Tribute", "At Last (Epic Trailer Version)")
    assert search.relevance(unrelated, "At Last") < search.RELEVANCE_FLOOR
    assert search.relevance(legit_cover, "At Last") >= search.RELEVANCE_FLOOR


def test_a_band_whose_name_contains_the_song_is_not_a_cover_of_it():
    """חיפוש "Happy" החזיר את הקטלוג של להקות ששמן מכיל את המילה:
    `token_set_ratio("happy", "demob happy")` הוא 100, ולכן "Demob Happy —
    Hades, Baby" קיבל בדיוק את הציון של "Pharrell Williams — Happy"."""
    band = make("Demob Happy", "Hades, Baby (Orchestral Version from Abbey Road)")
    real = make("Pharrell Williams", "Happy")
    cover = make("2WEI", "Happy (Epic Trailer Version)")

    assert search.relevance(band, "Happy") < search.RELEVANCE_FLOOR
    assert search.relevance(real, "Happy") >= search.RELEVANCE_FLOOR
    assert search.relevance(cover, "Happy") >= search.RELEVANCE_FLOOR


def test_the_artist_still_answers_when_the_query_is_an_artist():
    """"עוד באותו סגנון" מחפש לפי שם אמן או ז'אנר, ושם ההתאמה על האמן
    היא בדיוק מה שמבוקש."""
    anything = make("Tommee Profitt", "In the End")
    assert search.relevance(anything, "Tommee Profitt", match_artist=True) >= search.RELEVANCE_FLOOR
    assert search.relevance(anything, "Tommee Profitt") < search.RELEVANCE_FLOOR


def test_an_extra_word_in_the_title_makes_it_a_different_song():
    """אם לשיר קוראים "Happy", שם עם מילה נוספת הוא שיר אחר."""
    for title in ("Happy Birthday", "Happy Together", "Happy Acoustic",
                  "Epic Happy Trailer"):
        assert search.relevance(make("X", title), "Happy") < search.RELEVANCE_FLOOR, title


def test_the_trailer_words_are_cut_even_without_brackets():
    """מילים כמו Epic, Trailer, Trailerized ו-Soundtrack לעולם אינן חלק משם
    של שיר, ולכן הן נחתכות גם חשופות — בניגוד לכל שאר מילות הגרסה."""
    for title in ("Zombie Epic Trailer Version", "Zombie Trailerized",
                  "Zombie Soundtrack Version", "Zombie Epic", "Zombie Cover",
                  "Zombie Remix", "Zombie Version", "Zombie Instrumental"):
        assert search.relevance(make("X", title), "Zombie") >= search.RELEVANCE_FLOOR, title


def test_the_other_version_words_still_need_to_declare_themselves():
    """מילה חשופה שאינה ברשימה היא חלק מהשם."""
    assert search.relevance(make("X", "Happy Acoustic"), "Happy") < search.RELEVANCE_FLOOR
    assert search.relevance(make("X", "Happy (Acoustic)"), "Happy") >= search.RELEVANCE_FLOOR


def test_a_song_actually_named_after_a_trailer_word_still_matches():
    """חיתוך המילה משאיר מחרוזת ריקה, והנפילה לאחור היא הכותרת כמו שהיא."""
    assert search.relevance(make("X", "Epic"), "Epic") >= search.RELEVANCE_FLOOR
    assert search.relevance(make("X", "Soundtrack to My Life"),
                            "Soundtrack to My Life") >= search.RELEVANCE_FLOOR


def test_a_declared_version_is_still_the_same_song():
    """סוגריים ומקף הם האופן שבו iTunes ו-Deezer מסמנים גרסה, ולכן קאבר
    אמיתי אינו נפגע מהכלל שלמעלה."""
    for title in ("Happy", "Happy (Epic Trailer Version)", "Happy - Epic Version",
                  'Happy (From "Despicable Me 2")'):
        assert search.relevance(make("X", title), "Happy") >= search.RELEVANCE_FLOOR, title


def test_a_song_with_a_nearly_identical_name_is_not_a_cover():
    """המשתמש חיפש "My Way" וקיבל "On My Way" (שיר אחר) ו-"My War" (אות
    אחת הבדל). שניהם עברו את הרצפה הישנה של 65."""
    for title in ("On My Way (Trailer Version)", "My War (Attack on Titan)",
                  "My Way Home"):
        assert search.relevance(make("X", title), "My Way") < search.RELEVANCE_FLOOR, title


def test_the_floor_leaves_room_for_a_spelling_variant_of_the_real_song():
    """הרצפה גבוהה, אבל לא עד כדי דרישה לזהות תווים: אחרי הורדת תג הגרסה
    מה שנשאר הוא שם השיר, וּווריאציות ניסוח עדיין נופלות עליו."""
    for query, title in (
            ("My Way", "My Way (Epic Trailer Version)"),
            ("Bitter Sweet Symphony", "Bittersweet Symphony (Epic Trailer Version)"),
            ("California Dreaming", 'California Dreamin\' (From "San Andreas")'),
            ("Bring Me To Life", "Bring Me to Life (Cinematic Version)")):
        assert search.relevance(make("X", title), query) >= search.RELEVANCE_FLOOR, title


def test_relevance_survives_version_tags_on_the_candidate_title():
    """הכותרת מנוקה לפני ההשוואה — תג הגרסה לא מוריד את הציון."""
    tagged = make("2WEI", "Zombie (Epic Trailer Version)")
    assert search.relevance(tagged, "Zombie") == 100


def test_search_covers_excludes_unrelated_titles_below_the_relevance_floor(monkeypatch):
    pool = [make("Beyoncé", "At Last (Album Version)", uid="a"),
           make("Danny Elfman", "At Long Last, Love", uid="b")]
    monkeypatch.setattr(search, "itunes_search", lambda *a, **k: list(pool))
    monkeypatch.setattr(search, "deezer_search", lambda *a, **k: [])

    results = search.search_covers("At Last", include_seeds=False)
    assert {t["artist"] for t in results} == {"Beyoncé"}


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


# ---------- ריענון כתובות תצוגה מקדימה ----------

def test_refresh_preview_asks_itunes_by_the_saved_id(monkeypatch):
    """`uid` נשמר עם כל גרסה בדיוק בשביל זה."""
    seen = {}

    def fake_get_json(url, **kwargs):
        seen["url"] = url
        return {"results": [{"previewUrl": "https://new/preview.m4a"}]}

    monkeypatch.setattr(search, "get_json", fake_get_json)
    entry = {"uid": "itunes-123", "artist": "2WEI", "track": "Zombie"}
    assert search.refresh_preview(entry) == ("https://new/preview.m4a", "itunes-123")
    assert "id=123" in seen["url"]


def test_refresh_preview_asks_deezer_by_the_saved_id(monkeypatch):
    monkeypatch.setattr(search, "get_json", lambda url, **k: {"preview": "https://new/p.mp3"})
    entry = {"uid": "deezer-456", "artist": "2WEI", "track": "Zombie"}
    assert search.refresh_preview(entry) == ("https://new/p.mp3", "deezer-456")


def test_refresh_preview_falls_back_to_a_search_for_an_entry_with_no_id(monkeypatch):
    """רשומות שנשמרו לפני ש-uid נכנס לשמירה — ההתאמה לפי `track_key`."""
    monkeypatch.setattr(search, "get_json", lambda url, **k: None)
    monkeypatch.setattr(search, "itunes_search", lambda *a, **k: [
        make("Somebody Else", "Zombie", uid="x", preview="https://preview/x"),
        make("2WEI", "Zombie (Epic Trailer Version)", uid="y", preview="https://preview/y"),
    ])
    entry = {"artist": "2WEI", "track": "Zombie (Epic Trailer Version)"}
    assert search.refresh_preview(entry) == ("https://preview/y", "y")


def test_refresh_preview_returns_empty_when_nothing_matches(monkeypatch):
    """כתובת ריקה ולא כתובת שגויה: גרסה שלא נמצאה נשארת כפי שהיא."""
    monkeypatch.setattr(search, "get_json", lambda url, **k: None)
    monkeypatch.setattr(search, "itunes_search", lambda *a, **k: [])
    monkeypatch.setattr(search, "deezer_search", lambda *a, **k: [])
    assert search.refresh_preview({"artist": "A", "track": "B"}) == ("", "")


def test_a_query_with_brackets_matches_its_own_title():
    """הניקוי הופעל על הכותרת בלבד ולא על השאילתה, ולכן שאילתה שיש בה
    סוגריים לא יכלה להתאים אפילו לכותרת הזהה לה — "(Sittin' On) The Dock
    Of The Bay" קיבל 77 מול עצמו, ומאז שהרצפה עלתה ל-90 פשוט לא הוחזר."""
    for title in ("(Sittin' On) The Dock Of The Bay",
                  "Nel Blu Dipinto Di Blu (Volare)",
                  "Aquarius/Let The Sunshine In (The Flesh Failures)",
                  "Roses Are Red (My Love)"):
        assert search.relevance(make("X", title), title) >= search.RELEVANCE_FLOOR, title


def test_the_short_and_the_full_form_of_a_title_find_each_other():
    full = "(Sittin' On) The Dock Of The Bay"
    assert search.relevance(make("X", "The Dock Of The Bay (Epic Trailer Version)"),
                            full) >= search.RELEVANCE_FLOOR


def test_refresh_preview_returns_the_id_so_the_next_refresh_is_direct(monkeypatch):
    """רשומה שנשמרה לפני שהשדה קיים מקבלת uid בריענון הראשון, והבא יהיה
    שאילתת lookup ישירה במקום חיפוש בחנות."""
    monkeypatch.setattr(search, "get_json", lambda url, **k: None)
    monkeypatch.setattr(search, "itunes_search", lambda *a, **k: [
        make("2WEI", "Zombie", uid="itunes-77", preview="https://p/77")])
    url, uid = search.refresh_preview({"artist": "2WEI", "track": "Zombie"})
    assert (url, uid) == ("https://p/77", "itunes-77")
