from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import sqlite3
import os
from datetime import datetime
import json
import time
import requests

from google.genai import Client

client = Client(api_key="api key")

NEWS_PORTALS = {
    "onlinekhabar": {
        "name": "Online Khabar",
        "url": "https://www.onlinekhabar.com/",
        "selector": "section.ok-bises.ok-bises-type-2 h2",
        "link_tag": "a",
        "language": "np",
    },
    "baahrakhari": {
        "name": "Baahrakhari",
        "url": "https://baahrakhari.com/",
        "selector": "section.section.breaking-section.break-section div.container",
        "link_tag": "a",
        "language": "np",
    },
    "deshsanchar": {
        "name": "Desh Sanchar",
        "url": "https://deshsanchar.com/",
        "selector": "section.fp-special-news-section div.ds-container",
        "link_tag": "a",
        "language": "np",
    },
    "annapurnapost": {
        "name": "Annapurna Post",
        "url": "https://annapurnapost.com/",
        "selector": "div.ap__breakingNews div.breaking__news",
        "link_tag": "a",
        "language": "np",
    },
    "setopati": {
        "name": "Setopati",
        "url": "https://www.setopati.com/",
        "selector": "section.section.breaking-news",
        "link_tag": "a",
        "language": "np",
    },
    "ratopati": {
        "name": "Ratopati",
        "url": "https://www.ratopati.com/category/headline-news",
        "selector": "div.samachar-section",
        "link_tag": "a",
        "language": "np",
    },
    "ujyaaloonline": {
        "name": "Ujyaalo Online",
        "url": "https://ujyaaloonline.com/",
        "selector": "div.row.text-center.clearfix.bg-white.mb-15",
        "link_tag": "a",
        "language": "np",
    },
    "nagariknews": {
        "name": "Nagarik News",
        "url": "https://nagariknews.nagariknetwork.com/",
        "selector": "div.text-center.border-bottom.pb-4",
        "link_tag": "a",
        "language": "np",
    },
    "himalyantimes": {
        "name": "The Himalayan Times",
        "url": "https://thehimalayantimes.com/",
        "selector": "div.ht-homepage-left-one-article",
        "link_tag": "a",
        "language": "en",
    },
}

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(BASE_DIR, "portal_archive", "database.db")
THUMB_DIR = os.path.join(BASE_DIR, "portal_archive", "thumbnails")

os.makedirs(THUMB_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS portals (
            portal_key      TEXT    PRIMARY KEY,
            portal_name     TEXT    NOT NULL,
            base_url        TEXT    NOT NULL,
            selector        TEXT    NOT NULL,
            link_tag        TEXT    NOT NULL DEFAULT 'a',
            language        TEXT    NOT NULL DEFAULT 'np'
                CHECK (language IN ('np', 'en')),
            last_scraped_at TEXT,
            is_active       INTEGER NOT NULL DEFAULT 1
                CHECK (is_active IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS articles (
            article_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            article_url     TEXT    UNIQUE NOT NULL,
            portal_key      TEXT    NOT NULL
                REFERENCES portals(portal_key),
            title           TEXT,
            clean_content   TEXT,
            summary_en      TEXT,
            keywords_en     TEXT,
            summary_np      TEXT,
            keywords_np     TEXT,
            first_seen_date TEXT    NOT NULL
                CHECK (first_seen_date LIKE '____-__-__')
        );

        CREATE TABLE IF NOT EXISTS headline_snapshots (
            snapshot_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            scrape_datetime    TEXT    NOT NULL,
            portal_key         TEXT    NOT NULL
                REFERENCES portals(portal_key),
            article_id         INTEGER NOT NULL
                REFERENCES articles(article_id),
            thumbnail_filename TEXT,
            thumbnail_path     TEXT,
            UNIQUE (scrape_datetime, portal_key)
        );
    """)

    for key, cfg in NEWS_PORTALS.items():
        c.execute("""
            INSERT INTO portals
                (portal_key, portal_name, base_url, selector, link_tag, language)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(portal_key) DO UPDATE SET
                portal_name = excluded.portal_name,
                base_url    = excluded.base_url,
                selector    = excluded.selector,
                link_tag    = excluded.link_tag,
                language    = excluded.language
        """, (key, cfg["name"], cfg["url"],
              cfg["selector"], cfg["link_tag"], cfg["language"]))

    conn.commit()
    conn.close()


def extract_title_from_jina_text(text: str) -> str:
    """Return text after the first 'Title:' line in Jina-cleaned output."""
    if not text:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("title:"):
            return stripped[6:].strip()
    return ""


def get_clean_article_text(url: str) -> str:
    if not url:
        return ""
    try:
        resp = requests.get(
            f"https://r.jina.ai/{url}",
            timeout=16,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"},
        )
        resp.raise_for_status()
        return resp.text.strip()
    except Exception as e:
        print(f"  Jina failed → {url[:90]} → {e}")
        return ""


def summarize_with_gemini(url: str, lang: str = "en") -> tuple[str, str]:
    if not url:
        return "", ""

    if lang == "en":
        prompt = f"""Summarize the main news article at this URL in English.
                    Be concise (max 90-110 words). Focus on key facts.
                    Extract 5-10 important keywords (comma separated).
                    Return ONLY valid JSON with no markdown fences:
                    {{"summary": "...", "keywords": "kw1,kw2,kw3"}}
                    URL: {url}"""
    else:
        prompt = f"""यो URL मा रहेको मुख्य समाचारको नेपालीमा संक्षिप्त सारांश लेख्नुहोस्।
                    अधिकतम ९०-११० शब्द। मुख्य तथ्यमा केन्द्रित रहनुहोस्।
                    ५-१० मुख्य किवर्डहरू कमाले छुट्ट्याएर दिनुहोस्।
                    केवल valid JSON फर्काउनुहोस् — markdown fence नराख्नुस्:
                    {{"summary": "...", "keywords": "kw1,kw2,kw3"}}
                    URL: {url}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw   = response.text.strip()
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start == -1 or end <= start:
            return "", ""
        data = json.loads(raw[start:end])
        return data.get("summary", "").strip(), data.get("keywords", "").strip()
    except Exception as e:
        print(f"  Gemini {lang.upper()} failed → {url[:80]} → {str(e)[:140]}")
        return "", ""

def scrape_today():
    now      = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    live_str = now.isoformat(timespec="seconds")
    init_db()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    for key, portal in NEWS_PORTALS.items():
        driver = None
        try:
            driver = webdriver.Chrome(options=options)
            driver.get(portal["url"])

            wait_secs = 16 if key in ("onlinekhabar", "ratopati", "himalyantimes", "setopati") else 9
            time.sleep(wait_secs)

            wait        = WebDriverWait(driver, 22)
            headline_el = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, portal["selector"]))
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", headline_el
            )
            wait.until(lambda d: headline_el.size["height"] > 10)

            filename   = f"{key}_{date_str}_{now.strftime('%H%M%S')}.png"
            thumb_path = os.path.join(THUMB_DIR, filename)
            headline_el.screenshot(thumb_path)

            link_el     = headline_el.find_element(By.TAG_NAME, portal["link_tag"])
            article_url = (link_el.get_attribute("href") or "").strip()

            if not article_url.startswith("http"):
                print(f"  ⚠  Invalid URL skipped: {article_url!r}")
                continue
            clean_text = get_clean_article_text(article_url)
            title      = extract_title_from_jina_text(clean_text)
            summary_en, kw_en = summarize_with_gemini(article_url, "en")
            summary_np, kw_np = summarize_with_gemini(article_url, "np")

            # ON CONFLICT: keep existing non-empty values; only fill blanks.
            c.execute("""
                INSERT INTO articles
                    (article_url, portal_key, title, clean_content,
                     summary_en, keywords_en, summary_np, keywords_np,
                     first_seen_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_url) DO UPDATE SET
                    title         = COALESCE(NULLIF(excluded.title,''),         articles.title),
                    clean_content = COALESCE(NULLIF(excluded.clean_content,''), articles.clean_content),
                    summary_en    = COALESCE(NULLIF(excluded.summary_en,''),    articles.summary_en),
                    keywords_en   = COALESCE(NULLIF(excluded.keywords_en,''),   articles.keywords_en),
                    summary_np    = COALESCE(NULLIF(excluded.summary_np,''),    articles.summary_np),
                    keywords_np   = COALESCE(NULLIF(excluded.keywords_np,''),   articles.keywords_np)
            """, (article_url, key, title, clean_text,
                  summary_en, kw_en, summary_np, kw_np, date_str))

            article_id = c.execute(
                "SELECT article_id FROM articles WHERE article_url = ?",
                (article_url,)
            ).fetchone()[0]

            c.execute("""
                INSERT OR IGNORE INTO headline_snapshots
                    (scrape_datetime, portal_key, article_id,
                     thumbnail_filename, thumbnail_path)
                VALUES (?, ?, ?, ?, ?)
            """, (live_str, key, article_id, filename, thumb_path))

            c.execute(
                "UPDATE portals SET last_scraped_at = ? WHERE portal_key = ?",
                (live_str, key)
            )
            conn.commit()

            print(f"{portal['name']:22} | {filename}")
            print(f"URL   : {article_url[:78]}")
            print(f"Title : {(title or '(none)')[:72]}")
            print(f"EN    : {(summary_en or '(empty)')[:65]}")
            print(f"NP    : {(summary_np or '(empty)')[:65]}")
            print()

            time.sleep(2.4)

        except Exception as e:
            print(f"{portal['name']:22} → {str(e)[:140]}\n")
        finally:
            if driver is not None:
                driver.quit()

    conn.close()
    print(f"Finished")

if __name__ == "__main__":
    scrape_today()