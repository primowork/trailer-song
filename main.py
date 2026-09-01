from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
import httpx
from bs4 import BeautifulSoup
import urllib.parse

app = FastAPI(title="IFPI Israel Auto-Finder")

# כתובת מנוע החיפוש של הפדרציה הישראלית
IFPI_SEARCH_URL = "https://www.federation.co.il/Index.asp"

async def check_ifpi_status(artist: str, track: str) -> bool:
    """סורק את אתר הפדרציה הישראלית לבדיקת ייצוג בזמן אמת"""
    params = {
        "CategoryID": "94",
        "artName": artist,
        "trkName": track
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        try:
            response = await client.get(IFPI_SEARCH_URL, params=params, headers=headers)
            soup = BeautifulSoup(response.text, "html.parser")
            
            # בדיקה אם קיימות שורות תוצאה בטבלה
            # אם מופיעה הודעת "לא נמצאו תוצאות" או טבלה ריקה -> False
            table = soup.find("table", {"id": "searchResults"}) or soup.find("tr", class_="resultRow")
            if table and "מיוצג" in response.text:
                return True
            return False
        except Exception:
            return False

@app.get("/search")
async def search_and_verify(q: str = Query(..., description="מילת חיפוש, למשל: trailer cover victory")):
    """שולף שירים מ-iTunes חופשי ומחזיר רק את אלה המאושרים בפדרציה"""
    # 1. חיפוש שירים ב-iTunes API (חינמי לחלוטין, ללא הרשמה)
    itunes_url = f"https://itunes.apple.com/search?term={urllib.parse.quote(q)}&media=music&entity=song&limit=25"
    
    async with httpx.AsyncClient() as client:
        res = await client.get(itunes_url)
        data = res.json()
        
    raw_tracks = data.get("results", [])
    approved_tracks = []

    # 2. סינון אקטיבי מול הפדרציה
    for item in raw_tracks:
        artist_name = item.get("artistName", "")
        track_name = item.get("trackName", "")
        
        # ניקוי סוגריים וגרסאות בשם השיר לחיפוש מדויק בפדרציה
        clean_track = track_name.split("(")[0].strip()
        
        is_approved = await check_ifpi_status(artist_name, clean_track)
        
        if is_approved:
            approved_tracks.append({
                "artist": artist_name,
                "track": track_name,
                "original_collection": item.get("collectionName"),
                "preview_url": item.get("previewUrl"),
                "status": "🟢 APPROVED"
            })

    return {
        "query": q,
        "total_found_in_store": len(raw_tracks),
        "total_approved_in_federation": len(approved_tracks),
        "results": approved_tracks
    }

@app.get("/", response_class=HTMLResponse)
async def home_ui():
    """ממשק משתמש בסיסי לבדיקה בדפדפן"""
    return """
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <title>סורק קאברים מאושרים - פדרציה</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f4f4f9; }
            input, button { padding: 10px; font-size: 16px; margin: 5px; }
            .card { background: white; padding: 15px; margin-bottom: 10px; border-radius: 8px; border-right: 5px solid #2ecc71; }
        </style>
    </head>
    <body>
        <h1>🔎 סורק קאברים אקטיבי מול הפדרציה (ללא ספוטיפיי)</h1>
        <input type="text" id="query" placeholder="הכנס נושא (למשל: trailer victory cover)" style="width: 300px;">
        <button onclick="runSearch()">חפש שירים מאושרים</button>
        <div id="results" style="margin-top: 20px;"></div>

        <script>
            async function runSearch() {
                const q = document.getElementById('query').value;
                const div = document.getElementById('results');
                div.innerHTML = 'סורק ומאמת מול מאגר הפדרציה... אנא המתן...';
                
                const res = await fetch('/search?q=' + encodeURIComponent(q));
                const data = await res.json();
                
                div.innerHTML = `<h3>נמצאו ${data.total_approved_in_federation} שירים מאושרים:</h3>`;
                data.results.forEach(item => {
                    div.innerHTML += `
                        <div class="card">
                            <strong>${item.artist} - ${item.track}</strong><br>
                            <small>סטטוס: ${item.status}</small><br>
                            ${item.preview_url ? `<audio controls src="${item.preview_url}"></audio>` : ''}
                        </div>
                    `;
                });
            }
        </script>
    </body>
    </html>
    """
