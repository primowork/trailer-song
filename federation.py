"""אימות ייצוג מול אתר הפדרציה הישראלית (federation.co.il).

שני שיפורים מרכזיים על הגרסה הקודמת:
1. מהירות — דפדפן אחד לכל האצווה במקום דפדפן לכל שיר, ניסיון HTTP מהיר לפני
   הרמת דפדפן בכלל, וקאש תוצאות.
2. דיוק — התאמה דורשת גם אמן וגם שם שיר, והמייצג נלקח מעמודה מזוהה. כישלון
   סריקה מוחזר כ-UNKNOWN ולא כ"לא מיוצג".
"""
from dataclasses import dataclass, asdict

import httpx
from bs4 import BeautifulSoup
from thefuzz import fuzz

from search import clean_artist_name, clean_track_title

FEDERATION_URL = "https://www.federation.co.il/Index.asp"
CATEGORY_ID = "94"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

APPROVED = "APPROVED"
NOT_FOUND = "NOT_FOUND"
UNKNOWN = "UNKNOWN"

NO_RESULTS_MARKERS = ("לא נמצאו תוצאות", "לא נמצאו רשומות")

PUBLISHER_HINTS = (
    "יוניברסל", "וורנר", "סוני", "הליקון", "אן.אמ.סי", "מיוצג",
    "nmc", "bmg", "universal", "sony", "warner", "helicon",
)

PUBLISHER_HEADERS = ("מייצג", "חברה", "מפיץ", "בעל זכויות", "לייבל")

ARTIST_MATCH_THRESHOLD = 85
TRACK_MATCH_THRESHOLD = 80
PUBLISHER_COLUMN_FALLBACK = 4  # אינדקס העמודה ששימש בגרסה הקודמת


@dataclass
class VerifyResult:
    status: str = UNKNOWN
    publisher: str = ""
    confidence: int = 0
    matched_row: str = ""
    strategy: str = ""
    error: str = ""

    @property
    def approved(self) -> bool:
        return self.status == APPROVED

    def to_dict(self) -> dict:
        return asdict(self)


def _find_publisher_column(table) -> int | None:
    """מאתר את עמודת המייצג לפי כותרות הטבלה, אם קיימות."""
    if table is None:
        return None
    for row in table.find_all("tr")[:3]:
        headers = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
        for idx, header in enumerate(headers):
            if any(h in header for h in PUBLISHER_HEADERS):
                return idx
    return None


def parse_ifpi_table(html_content: str, target_artist: str, target_track: str = "") -> VerifyResult:
    """מנתח את תוצאת החיפוש. דורש התאמה של אמן *וגם* שיר."""
    if not html_content:
        return VerifyResult(status=UNKNOWN, error="תוכן ריק")

    try:
        soup = BeautifulSoup(html_content, "html.parser")
    except Exception as exc:
        return VerifyResult(status=UNKNOWN, error=f"פרסור נכשל: {exc}")

    text = soup.get_text(" ", strip=True)
    if any(marker in text for marker in NO_RESULTS_MARKERS):
        return VerifyResult(status=NOT_FOUND, confidence=95)

    rows = soup.find_all("tr")
    if not rows:
        # אין טבלה בכלל — לא ידוע אם החיפוש בכלל רץ
        return VerifyResult(status=UNKNOWN, error="לא נמצאה טבלת תוצאות")

    clean_artist = clean_artist_name(target_artist).lower()
    clean_track = clean_track_title(target_track).lower()
    publisher_idx = _find_publisher_column(soup.find("table"))

    best = VerifyResult(status=NOT_FOUND, confidence=60)

    for row in rows:
        cols = [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]
        if not cols:
            continue
        row_text = " ".join(cols).lower()

        artist_score = fuzz.token_set_ratio(clean_artist, row_text) if clean_artist else 0
        track_score = fuzz.partial_ratio(clean_track, row_text) if clean_track else 0

        # דרישת התאמה כפולה — כאן נחסמות התוצאות השגויות של הגרסה הקודמת
        if artist_score < ARTIST_MATCH_THRESHOLD:
            continue
        if clean_track and track_score < TRACK_MATCH_THRESHOLD:
            continue

        publisher = ""
        if publisher_idx is not None and len(cols) > publisher_idx:
            publisher = cols[publisher_idx]
        if not publisher and len(cols) > PUBLISHER_COLUMN_FALLBACK:
            publisher = cols[PUBLISHER_COLUMN_FALLBACK]
        publisher = publisher.strip()

        if not publisher or publisher in {"-", "--"} or len(publisher) < 2:
            continue

        confidence = int((artist_score + (track_score if clean_track else artist_score)) / 2)
        if any(hint in publisher.lower() for hint in PUBLISHER_HINTS):
            confidence = min(100, confidence + 10)

        if confidence > best.confidence or best.status != APPROVED:
            best = VerifyResult(
                status=APPROVED,
                publisher=publisher,
                confidence=min(confidence, 100),
                matched_row=" | ".join(cols)[:300],
            )

    return best


def _looks_like_results_page(html: str) -> bool:
    """האם התשובה נראית כמו עמוד תוצאות אמיתי ולא כמו שגיאה/עמוד ריק."""
    if not html or len(html) < 500:
        return False
    lowered = html.lower()
    if any(marker in html for marker in NO_RESULTS_MARKERS):
        return True
    return "<tr" in lowered and 'name="artname"' in lowered


def _http_search(artist: str, track: str, client: httpx.Client) -> str:
    """ניסיון מהיר ללא דפדפן. מחזיר HTML או מחרוזת ריקה אם לא התאים."""
    params = {"CategoryID": CATEGORY_ID, "artName": artist, "trkName": track}
    try:
        response = client.get(FEDERATION_URL, params=params,
                              headers={"User-Agent": USER_AGENT}, timeout=10.0)
        html = response.text
    except Exception:
        return ""
    return html if _looks_like_results_page(html) else ""


class FederationClient:
    """מחזיק דפדפן אחד לכל האצווה. שימוש כ-context manager.

    with FederationClient() as fed:
        result = fed.verify(track)
    """

    def __init__(self, use_http_fast_path: bool = True, debug: bool = False):
        self.use_http_fast_path = use_http_fast_path
        self.debug = debug
        self.last_html = ""
        self._playwright = None
        self._browser = None
        self._page = None
        self._http = httpx.Client(follow_redirects=True, timeout=10.0)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def close(self):
        for closer in (
            lambda: self._page and self._page.close(),
            lambda: self._browser and self._browser.close(),
            lambda: self._playwright and self._playwright.stop(),
            lambda: self._http.close(),
        ):
            try:
                closer()
            except Exception:
                pass
        self._page = self._browser = self._playwright = None

    # ---------- מסלול Playwright ----------

    def _ensure_page(self):
        """מרים דפדפן פעם אחת בלבד, בעצלתיים."""
        if self._page is not None:
            return self._page
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = self._browser.new_context(user_agent=USER_AGENT)
        self._page = context.new_page()
        return self._page

    def _browser_search(self, artist: str, track: str) -> str:
        page = self._ensure_page()
        page.goto(f"{FEDERATION_URL}?CategoryID={CATEGORY_ID}",
                  wait_until="domcontentloaded", timeout=20000)
        page.fill('input[name="artName"]', artist)
        page.fill('input[name="trkName"]', track)
        with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
            page.locator(
                'input[type="submit"], input[value="חפש"], button[type="submit"]'
            ).first.click()
        page.wait_for_timeout(1200)
        return page.content()

    def _search(self, artist: str, track: str) -> str:
        if self.use_http_fast_path:
            html = _http_search(artist, track, self._http)
            if html:
                return html
        return self._browser_search(artist, track)

    # ---------- API ----------

    def verify(self, track: dict) -> VerifyResult:
        """שלוש אסטרטגיות בסדר יורד של ביטחון."""
        raw_artist = track.get("artist") or track.get("artistName") or ""
        raw_song = track.get("track") or track.get("trackName") or ""

        clean_song = clean_track_title(raw_song)
        clean_artist = clean_artist_name(raw_artist)
        # חיתוך ל-2 מילים ראשונות — עוקף שינויי כתיב בין iTunes לפדרציה
        short_artist = " ".join(clean_artist.split()[:2])

        strategies = [
            ("אמן + שיר", short_artist, clean_song, 0),
            ("שיר בלבד", "", clean_song, 5),
            ("אמן בלבד", short_artist, "", 20),
        ]

        last_error = ""
        saw_response = False

        for name, artist_param, track_param, penalty in strategies:
            if not artist_param and not track_param:
                continue
            try:
                html = self._search(artist_param, track_param)
            except Exception as exc:
                last_error = str(exc)
                continue

            saw_response = True
            if self.debug:
                self.last_html = html

            # באסטרטגיה "אמן בלבד" אין שם שיר לאמת מולו — ההתאמה חלשה יותר
            result = parse_ifpi_table(html, raw_artist, "" if not track_param else raw_song)
            result.strategy = name
            if result.status == APPROVED:
                result.confidence = max(0, result.confidence - penalty)
                return result

        if not saw_response:
            return VerifyResult(status=UNKNOWN, error=last_error or "כל הניסיונות נכשלו")
        return VerifyResult(status=NOT_FOUND, confidence=70, strategy="כל האסטרטגיות")

    def verify_many(self, tracks: list[dict], progress_cb=None) -> list[VerifyResult]:
        results = []
        total = len(tracks)
        for index, track in enumerate(tracks):
            results.append(self.verify(track))
            if progress_cb:
                progress_cb(index + 1, total, track)
        return results
