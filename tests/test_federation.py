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


def test_verify_returns_unknown_when_every_strategy_fails(monkeypatch):
    client = federation.FederationClient.__new__(federation.FederationClient)
    client.use_http_fast_path = False
    client.debug = False
    client.last_html = ""

    def boom(*args, **kwargs):
        raise RuntimeError("no network")

    client._search = boom
    result = federation.FederationClient.verify(client, {"artist": "2WEI", "track": "Survivor"})
    assert result.status == federation.UNKNOWN
    assert "no network" in result.error


def test_verify_stops_at_first_approval():
    calls = []
    client = federation.FederationClient.__new__(federation.FederationClient)
    client.use_http_fast_path = False
    client.debug = False
    client.last_html = ""

    def fake_search(artist, track):
        calls.append((artist, track))
        return RESULTS_HTML

    client._search = fake_search
    result = federation.FederationClient.verify(client, {"artist": "2WEI", "track": "Survivor"})
    assert result.status == federation.APPROVED
    assert len(calls) == 1  # לא ממשיכים לאסטרטגיות הבאות מיותרות
    assert result.strategy == "אמן + שיר"
