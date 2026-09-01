import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import federation

RESULTS_HTML = """
<html><body>
<table>
  <tr><th>אמן</th><th>שם השיר</th><th>אלבום</th><th>שנה</th><th>מייצג</th></tr>
  <tr><td>2WEI</td><td>Survivor</td><td>Escalation</td><td>2019</td><td>יוניברסל</td></tr>
  <tr><td>Hidden Citizens</td><td>Paint It Black</td><td>Rise</td><td>2018</td><td>Sony Music</td></tr>
</table>
</body></html>
"""

NO_PUBLISHER_HTML = """
<html><body><table>
  <tr><th>אמן</th><th>שם השיר</th><th>אלבום</th><th>שנה</th><th>מייצג</th></tr>
  <tr><td>2WEI</td><td>Survivor</td><td>Escalation</td><td>2019</td><td>-</td></tr>
</table></body></html>
"""


def test_exact_match_is_approved_with_publisher():
    result = federation.parse_ifpi_table(RESULTS_HTML, "2WEI", "Survivor (Epic Trailer Version)")
    assert result.status == federation.APPROVED
    assert result.publisher == "יוניברסל"
    assert result.confidence >= 85
    assert "Survivor" in result.matched_row


def test_right_artist_wrong_song_is_not_approved():
    """הרגרסיה המרכזית: הגרסה הקודמת התאימה לפי אמן בלבד והחזירה 'מיוצג' בטעות."""
    result = federation.parse_ifpi_table(RESULTS_HTML, "2WEI", "Some Completely Other Song")
    assert result.status == federation.NOT_FOUND


def test_unrelated_artist_is_not_approved():
    result = federation.parse_ifpi_table(RESULTS_HTML, "Totally Unknown Band", "Survivor")
    assert result.status == federation.NOT_FOUND


def test_explicit_no_results_message():
    result = federation.parse_ifpi_table("<html><body>לא נמצאו תוצאות</body></html>", "2WEI", "Survivor")
    assert result.status == federation.NOT_FOUND
    assert result.confidence == 95


def test_page_without_table_is_unknown():
    """כישלון סריקה חייב להיות UNKNOWN ולא 'לא מיוצג' — זה מה שהטעה את המשתמש."""
    result = federation.parse_ifpi_table("<html><body><p>שגיאת שרת</p></body></html>", "2WEI", "Survivor")
    assert result.status == federation.UNKNOWN
    assert result.error


def test_empty_content_is_unknown():
    assert federation.parse_ifpi_table("", "2WEI", "Survivor").status == federation.UNKNOWN


def test_row_without_publisher_is_not_approved():
    result = federation.parse_ifpi_table(NO_PUBLISHER_HTML, "2WEI", "Survivor")
    assert result.status == federation.NOT_FOUND


def test_publisher_column_detected_from_headers():
    assert federation._find_publisher_column(
        __import__("bs4").BeautifulSoup(RESULTS_HTML, "html.parser").find("table")
    ) == 4


def test_known_publisher_boosts_confidence():
    plain = RESULTS_HTML.replace("<td>יוניברסל</td>", "<td>אולפני קול</td>")
    boosted = federation.parse_ifpi_table(RESULTS_HTML, "2WEI", "Survivor")
    unboosted = federation.parse_ifpi_table(plain, "2WEI", "Survivor")
    assert boosted.confidence >= unboosted.confidence


def test_looks_like_results_page():
    assert not federation._looks_like_results_page("")
    assert not federation._looks_like_results_page("<html>too short</html>")
    assert federation._looks_like_results_page(
        '<html><form><input name="artName"></form><table><tr><td>x</td></tr></table>' + "x" * 600 + "</html>"
    )


def test_verify_result_helpers():
    result = federation.VerifyResult(status=federation.APPROVED, publisher="Sony", confidence=90)
    assert result.approved
    assert result.to_dict()["publisher"] == "Sony"
    assert not federation.VerifyResult(status=federation.NOT_FOUND).approved


FORM_HTML = """
<html><body><form action="search.asp" method="get">
  <input type="text" name="artName">
  <input type="text" name="trkName">
  <input type="submit" value="חפש">
</form></body></html>
"""

NO_FORM_HTML = "<html><body><p>ברוכים הבאים</p></body></html>"


def _client_with_form(fields=("artName", "trkName")):
    """לקוח שה-preflight שלו כבר הצליח, בלי לגעת ברשת."""
    client = federation.FederationClient.__new__(federation.FederationClient)
    client.use_http_fast_path = False
    client.debug = False
    client.last_html = ""
    client.artist_field, client.track_field = fields
    client.preflight_error = ""
    client._preflight_done = True
    return client


def test_field_detection_picks_the_name_present_in_the_page():
    assert federation._first_present_field(FORM_HTML, [None, "artist", "artName"]) == "artName"
    assert federation._first_present_field(FORM_HTML, ["nope", "trkName"]) == "trkName"
    assert federation._first_present_field(NO_FORM_HTML, ["artName", "artist"]) == ""


def test_field_detection_is_case_insensitive():
    html = '<form><input name="ArtistName"></form>'
    assert federation._first_present_field(html, ["artistname"]) == "ArtistName"


def test_preflight_failure_marks_unknown_without_touching_the_browser():
    """הבאג שהיה: 30 שניות timeout כפול שלוש אסטרטגיות כפול כל שיר."""
    client = federation.FederationClient.__new__(federation.FederationClient)
    client.use_http_fast_path = False
    client.debug = False
    client.last_html = ""
    client._preflight_done = False
    client.artist_field = client.track_field = ""
    client.preflight_error = ""

    class FakeResponse:
        text = NO_FORM_HTML

    class FakeHttp:
        def get(self, *a, **k):
            return FakeResponse()

    client._http = FakeHttp()

    def must_not_run(*a, **k):
        raise AssertionError("אסור להריץ חיפוש אחרי preflight שנכשל")

    client._search = must_not_run

    result = federation.FederationClient.verify(client, {"artist": "2WEI", "track": "Survivor"})
    assert result.status == federation.UNKNOWN
    assert result.strategy == "preflight"
    assert "לא זוהה" in result.error


def test_preflight_unreachable_page_is_unknown():
    client = federation.FederationClient.__new__(federation.FederationClient)
    client._preflight_done = False
    client.artist_field = client.track_field = ""
    client.preflight_error = ""
    client.debug = False

    class FakeHttp:
        def get(self, *a, **k):
            raise RuntimeError("connection refused")

    client._http = FakeHttp()
    assert client.preflight() is False
    assert "connection refused" in client.preflight_error


def test_verify_returns_unknown_when_every_strategy_fails():
    client = _client_with_form()

    def boom(*args, **kwargs):
        raise RuntimeError("no network")

    client._search = boom
    result = federation.FederationClient.verify(client, {"artist": "2WEI", "track": "Survivor"})
    assert result.status == federation.UNKNOWN
    assert "no network" in result.error


def test_verify_stops_at_first_approval():
    calls = []
    client = _client_with_form()

    def fake_search(artist, track):
        calls.append((artist, track))
        return RESULTS_HTML

    client._search = fake_search
    result = federation.FederationClient.verify(client, {"artist": "2WEI", "track": "Survivor"})
    assert result.status == federation.APPROVED
    assert len(calls) == 1  # לא ממשיכים לאסטרטגיות הבאות מיותרות
    assert result.strategy == "אמן + שיר"


def test_strategies_needing_a_missing_field_are_skipped():
    """אם בטופס אין שדה אמן, אין טעם לנסות אסטרטגיה שדורשת אותו."""
    calls = []
    client = _client_with_form(fields=("", "trkName"))

    def fake_search(artist, track):
        calls.append((artist, track))
        return "<html><body>לא נמצאו תוצאות</body></html>"

    client._search = fake_search
    federation.FederationClient.verify(client, {"artist": "2WEI", "track": "Survivor"})
    assert all(artist == "" for artist, _ in calls)


def test_target_is_the_record_federation_not_the_anti_counterfeiting_one():
    """רגרסיה: federation.co.il הוא ארגון אחר לגמרי."""
    assert "ifpi.co.il" in federation.FEDERATION_URL
    assert "federation.co.il" not in federation.FEDERATION_URL


# ---------- נפילה לאחור בטעינת דף ה-preflight ----------

def _bare_client():
    client = federation.FederationClient.__new__(federation.FederationClient)
    client.use_http_fast_path = True
    client.debug = False
    client.last_html = ""
    client._preflight_done = False
    client.artist_field = client.track_field = ""
    client.preflight_error = ""
    return client


class _FailingHttp:
    def __init__(self):
        self.calls = 0

    def get(self, *a, **k):
        self.calls += 1
        raise RuntimeError("timed out")


def test_http_timeout_falls_back_to_the_browser(monkeypatch):
    """הבאג: timeout של httpx ביטל את כל האצווה בלי לנסות את הדפדפן."""
    client = _bare_client()
    client._http = _FailingHttp()

    class FakePage:
        def goto(self, *a, **k):
            return None

        def content(self):
            return FORM_HTML

    client._ensure_page = lambda: FakePage()

    assert client.preflight() is True
    assert client.artist_field == "artName"
    assert client.use_http_fast_path is False  # אין טעם לנסות שוב HTTP לכל שיר


def test_http_preflight_is_retried_before_giving_up():
    client = _bare_client()
    http = _FailingHttp()
    client._http = http

    def no_browser():
        raise RuntimeError("no browser")

    client._ensure_page = no_browser
    client.preflight()
    assert http.calls == federation.PREFLIGHT_ATTEMPTS


def test_unreachable_from_both_paths_names_both_errors():
    client = _bare_client()
    client._http = _FailingHttp()

    def no_browser():
        raise RuntimeError("Executable doesn't exist")

    client._ensure_page = no_browser
    assert client.preflight() is False
    assert "timed out" in client.preflight_error
    assert "Executable" in client.preflight_error


def test_loaded_page_without_form_is_a_different_message():
    """'נטען אך אין טופס' חייב להיראות אחרת מ'לא ניתן לטעון'."""
    client = _bare_client()

    class OkHttp:
        def get(self, *a, **k):
            class R:
                text = NO_FORM_HTML
            return R()

    client._http = OkHttp()
    assert client.preflight() is False
    assert "נטען" in client.preflight_error
    assert "לא ניתן לטעון" not in client.preflight_error


def test_diagnose_reports_dns_failure():
    report = federation.diagnose("https://nonexistent.invalid/search.asp")
    assert report["host"] == "nonexistent.invalid"
    assert "נכשל" in report["dns"]
