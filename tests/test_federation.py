import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import federation

RESULTS_HTML = """
<html><body>
<table>
  <tr><th>המבצע</th><th>הקלטה</th><th>אלבום</th><th>הערות</th><th>מיוצג בפדרציה ע"י</th></tr>
  <tr><td>2WEI</td><td>Survivor</td><td>Escalation</td><td>2019</td><td>יוניברסל</td></tr>
  <tr><td>Hidden Citizens</td><td>Paint It Black</td><td>Rise</td><td>2018</td><td>Sony Music</td></tr>
</table>
</body></html>
"""

NO_PUBLISHER_HTML = """
<html><body><table>
  <tr><th>המבצע</th><th>הקלטה</th><th>אלבום</th><th>הערות</th><th>מיוצג בפדרציה ע"י</th></tr>
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
    soup = __import__("bs4").BeautifulSoup(RESULTS_HTML, "html.parser")
    assert federation._publisher_index(federation._extract_rows(soup)) == 4


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


# ---------- אתר שאינו נגיש מהשרת ----------

class _TimingOutHttp:
    def get(self, *a, **k):
        raise RuntimeError("timed out")


def test_both_paths_timing_out_explains_it_is_a_network_block(monkeypatch):
    """הפלט מהדיפלוימנט: HTTP timed out וגם Page.goto Timeout 30000ms."""
    monkeypatch.setattr(federation, "PROXY", "")
    client = _bare_client()
    client._http = _TimingOutHttp()

    def browser_timeout():
        raise RuntimeError("Page.goto: Timeout 30000ms exceeded.")

    client._ensure_page = browser_timeout
    assert client.preflight() is False
    assert "אינו נגיש מהרשת של השרת" in client.preflight_error
    assert "IFPI_PROXY" in client.preflight_error


def test_timeout_message_changes_once_a_proxy_is_configured(monkeypatch):
    monkeypatch.setattr(federation, "PROXY", "http://proxy.example:8080")
    client = _bare_client()
    client._http = _TimingOutHttp()

    def browser_timeout():
        raise RuntimeError("Page.goto: Timeout 30000ms exceeded.")

    client._ensure_page = browser_timeout
    client.preflight()
    assert "גם דרך ה-proxy" in client.preflight_error
    assert "IFPI_PROXY" not in client.preflight_error


def test_non_timeout_failure_keeps_the_generic_hint(monkeypatch):
    monkeypatch.setattr(federation, "PROXY", "")
    client = _bare_client()

    class Refused:
        def get(self, *a, **k):
            raise RuntimeError("connection refused")

    client._http = Refused()

    def browser_error():
        raise RuntimeError("net::ERR_CONNECTION_REFUSED")

    client._ensure_page = browser_error
    client.preflight()
    assert "אינו נגיש מהרשת של השרת" not in client.preflight_error
    assert "בדוק חיבור לפדרציה" in client.preflight_error


def test_http_client_passes_the_proxy_through(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(federation.httpx, "Client", FakeClient)
    monkeypatch.setattr(federation, "PROXY", "http://proxy.example:8080")
    federation._http_client()
    assert captured["proxy"] == "http://proxy.example:8080"


def test_http_client_omits_proxy_when_unset(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(federation.httpx, "Client", FakeClient)
    monkeypatch.setattr(federation, "PROXY", "")
    federation._http_client()
    assert "proxy" not in captured


def test_diagnose_separates_tcp_from_http():
    report = federation.diagnose("https://nonexistent.invalid/search.asp")
    assert "proxy" in report
    assert "נכשל" in report["dns"]


# ---------- מסלול ידני דרך הדפדפן (האתר חוסם את השרת) ----------

def test_learning_fields_from_a_real_form():
    learned = federation.learn_fields_from_html(FORM_HTML)
    assert learned["artist_field"] == "artName"
    assert learned["track_field"] == "trkName"


def test_hidden_inputs_are_not_offered_for_manual_choice():
    html = ('<form><input type="hidden" name="CategoryID" value="94">'
            '<input type="text" name="weird_a"><input type="text" name="weird_b"></form>')
    assert federation.all_input_names(html) == ["weird_a", "weird_b"]


def test_unknown_field_names_are_listed_for_the_user(monkeypatch):
    monkeypatch.setattr(federation.storage, "save_federation_fields", lambda f: True)
    html = '<form><input type="text" name="zzz1"><input type="text" name="zzz2"></form>'
    learned = federation.learn_fields_from_html(html)
    assert learned["artist_field"] == ""
    assert learned["all_inputs"] == ["zzz1", "zzz2"]


def test_page_without_inputs_learns_nothing():
    learned = federation.learn_fields_from_html(NO_FORM_HTML)
    assert learned["all_inputs"] == []


def test_search_url_uses_the_learned_field_names(monkeypatch):
    monkeypatch.setattr(federation, "learned_fields",
                        lambda: {"artist_field": "artName", "track_field": "trkName"})
    url = federation.build_search_url("2WEI feat. Edda Hayes",
                                      "Survivor (Epic Trailer Version)")
    assert "artName=2WEI" in url
    assert "trkName=Survivor" in url


def test_search_url_encodes_spaces_and_specials(monkeypatch):
    monkeypatch.setattr(federation, "learned_fields",
                        lambda: {"artist_field": "a", "track_field": "t"})
    url = federation.build_search_url("Guns N' Roses", "Sweet Child")
    assert " " not in url
    assert "%27" in url or "%26" in url or "+" in url


def test_search_url_without_learned_fields_is_the_plain_page(monkeypatch):
    """עדיף כתובת בסיסית מקישור עם פרמטרים שהומצאו."""
    monkeypatch.setattr(federation, "learned_fields",
                        lambda: {"artist_field": "", "track_field": ""})
    assert federation.build_search_url("A", "B") == federation.FEDERATION_URL


def test_pasted_results_produce_a_verdict():
    result = federation.verify_from_html(RESULTS_HTML, "2WEI", "Survivor")
    assert result.status == federation.APPROVED
    assert result.publisher == "יוניברסל"
    assert result.strategy == "הדבקה ידנית"


def test_pasted_results_still_reject_the_wrong_song():
    result = federation.verify_from_html(RESULTS_HTML, "2WEI", "Some Other Song")
    assert result.status == federation.NOT_FOUND


def test_pasted_garbage_is_unknown_not_a_verdict():
    assert federation.verify_from_html("<p>hi</p>", "2WEI", "Survivor").status == federation.UNKNOWN


def test_learned_fields_are_a_fallback_not_an_override(monkeypatch):
    """דף שגיאה לא אמור 'להצליח' preflight רק כי פעם נלמדו שמות."""
    monkeypatch.setattr(federation, "learned_fields",
                        lambda: {"artist_field": "artName", "track_field": "trkName"})
    client = _bare_client()

    class OkHttp:
        def get(self, *a, **k):
            class R:
                text = NO_FORM_HTML
            return R()

    client._http = OkHttp()
    assert client.preflight() is False


# ---------- המבנה האמיתי של ifpi.co.il: div-ים צפים, לא <table> ----------
# נבנה מה-HTML שהמשתמש הדביק מהאתר. לאתר אין אף <table>, ולכן חיפוש <tr>
# בלבד החזיר "לא נמצאה טבלת תוצאות" על כל דף תוצאות אמיתי.

IFPI_HEADER = '''
<div style="float:left;width:100%;font-family:OpenSansBold">
  <div style="float:right;width:13%" onclick="searchBy('performer')">המבצע</div>
  <div style="float:right;width:15%" onclick="searchBy('name')">הקלטה <br />(שם היצירה)</div>
  <div style="float:right;width:11%">הערות<br /> (גרסת הקלטה)</div>
  <div style="float:right;width:15%" onclick="searchBy('album')">אלבום</div>
  <div style="float:right;width:13%" onclick="searchBy('represent')">מיוצג<br /> בפדרציה ע"י</div>
  <div style="float:right;width:14%">חובה לבדוק<br />פירוט החרגות</div>
  <div style="float:right;width:14%">חובה לבדוק<br /> פירוט החרגות</div>
</div>
'''


def _ifpi_row(performer, recording, notes, album, publisher, row_id="o1"):
    return f'''
    <div class="om" id="{row_id}">
      <div style="float:right;width:13%">{performer}</div>
      <div style="float:right;width:15%">{recording}</div>
      <div style="float:right;width:11%">{notes}</div>
      <div style="float:right;width:15%">{album}</div>
      <div style="float:right;width:13%">{publisher}</div>
      <div style="float:right;width:14%">כן</div>
      <div style="float:right;width:14%">כן</div>
    </div>
    '''


IFPI_RESULTS = ("<html><body>" + IFPI_HEADER
                + _ifpi_row("2WEI", "Survivor", "Epic Trailer Version",
                            "Escalation", "יוניברסל", "o1")
                + _ifpi_row("Hidden Citizens", "Paint It Black", "", "Rise",
                            "Sony Music", "o2")
                + "</body></html>")


def test_the_real_site_has_no_table_element():
    """הנחת היסוד של הפרסור הקודם, שנשברה מול האתר האמיתי."""
    soup = __import__("bs4").BeautifulSoup(IFPI_RESULTS, "html.parser")
    assert soup.find("table") is None
    assert soup.find_all("tr") == []


def test_div_rows_are_extracted():
    soup = __import__("bs4").BeautifulSoup(IFPI_RESULTS, "html.parser")
    rows = federation._extract_rows(soup)
    assert any("2WEI" in " ".join(cols) for cols in rows)
    assert any("Hidden Citizens" in " ".join(cols) for cols in rows)


def test_publisher_column_found_in_the_div_layout():
    soup = __import__("bs4").BeautifulSoup(IFPI_RESULTS, "html.parser")
    assert federation._publisher_index(federation._extract_rows(soup)) == 4


def test_verdict_from_the_real_div_layout():
    result = federation.parse_ifpi_table(IFPI_RESULTS, "2WEI",
                                         "Survivor (Epic Trailer Version)")
    assert result.status == federation.APPROVED
    assert result.publisher == "יוניברסל"


def test_div_layout_still_rejects_the_wrong_song():
    result = federation.parse_ifpi_table(IFPI_RESULTS, "2WEI", "Totally Other Song")
    assert result.status == federation.NOT_FOUND


def test_header_row_is_never_treated_as_a_result():
    """שורת הכותרות מכילה 'מיוצג' ואסור שתיחשב להתאמה."""
    result = federation.parse_ifpi_table("<html><body>" + IFPI_HEADER + "</body></html>",
                                         "המבצע", "הקלטה")
    assert result.status != federation.APPROVED


def test_real_field_names_are_detected_from_the_live_page():
    """באתר האמיתי השדות הם artist/song, לא artName/trkName שניחשתי."""
    live_form = '''<form name="searchForm" method="get" action="search.asp">
      <input type="hidden" name="searchBy" /><input type="hidden" name="page" />
      <input class="is" name="artist" /><input class="is" name="song" />
      <input class="is" name="album" /><input name="exact" type="checkbox" />
    </form>'''
    learned = federation.learn_fields_from_html(live_form)
    assert learned["artist_field"] == "artist"
    assert learned["track_field"] == "song"
