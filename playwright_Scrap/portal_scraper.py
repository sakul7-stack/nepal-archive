from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
import sqlite3
import os
from datetime import datetime
import json
import time
import requests
from google.genai import Client

client = Client(api_key="")

NEWS_PORTALS = {
    "onlinekhabar":  {"name": "Online Khabar",      "url": "https://www.onlinekhabar.com/",                   "selector": "section.ok-bises.ok-bises-type-2 h2",                         "link_tag": "a", "language": "np"},
    "baahrakhari":   {"name": "Baahrakhari",         "url": "https://baahrakhari.com/",                        "selector": "section.section.breaking-section.break-section div.container", "link_tag": "a", "language": "np"},
    "deshsanchar":   {"name": "Desh Sanchar",        "url": "https://deshsanchar.com/",                        "selector": "section.fp-special-news-section div.ds-container",            "link_tag": "a", "language": "np"},
    "annapurnapost": {"name": "Annapurna Post",      "url": "https://annapurnapost.com/",                      "selector": "div.ap__breakingNews div.breaking__news",                     "link_tag": "a", "language": "np"},
    "setopati":      {"name": "Setopati",            "url": "https://www.setopati.com/",                       "selector": "section.section.breaking-news",                               "link_tag": "a", "language": "np"},
    "ratopati":      {"name": "Ratopati",            "url": "https://www.ratopati.com/category/headline-news", "selector": "div.samachar-section",                                        "link_tag": "a", "language": "np"},
    "ujyaaloonline": {"name": "Ujyaalo Online",      "url": "https://ujyaaloonline.com/",                      "selector": "div.home-news-section",                                       "link_tag": "a", "language": "np"},
    "nagariknews":   {"name": "Nagarik News",        "url": "https://nagariknews.nagariknetwork.com/",         "selector": "div.text-center.border-bottom.pb-4",                          "link_tag": "a", "language": "np"},
    "himalyantimes": {"name": "The Himalayan Times", "url": "https://thehimalayantimes.com/",                  "selector": "div.ht-homepage-left-one-article",                            "link_tag": "a", "language": "en"},
}

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(BASE_DIR, "portal_archive", "database.db")
THUMB_DIR = os.path.join(BASE_DIR, "portal_archive", "thumbnails")
os.makedirs(THUMB_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

BROWSER_ARGS = [
    "--no-sandbox", "--disable-gpu", "--mute-audio", "--disable-dev-shm-usage",
]


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS portals (
            portal_key TEXT PRIMARY KEY, portal_name TEXT NOT NULL,
            base_url TEXT NOT NULL, selector TEXT NOT NULL,
            link_tag TEXT NOT NULL DEFAULT 'a',
            language TEXT NOT NULL DEFAULT 'np' CHECK (language IN ('np','en')),
            last_scraped_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
        );
        CREATE TABLE IF NOT EXISTS articles (
            article_id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_url TEXT UNIQUE NOT NULL,
            portal_key TEXT NOT NULL REFERENCES portals(portal_key),
            title TEXT, clean_content TEXT,
            summary_en TEXT, keywords_en TEXT,
            summary_np TEXT, keywords_np TEXT,
            first_seen_date TEXT NOT NULL CHECK (first_seen_date LIKE '____-__-__')
        );
        CREATE TABLE IF NOT EXISTS headline_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            scrape_datetime TEXT NOT NULL,
            portal_key TEXT NOT NULL REFERENCES portals(portal_key),
            article_id INTEGER NOT NULL REFERENCES articles(article_id),
            thumbnail_filename TEXT, thumbnail_path TEXT,
            UNIQUE (scrape_datetime, portal_key)
        );
    """)
    for key, cfg in NEWS_PORTALS.items():
        c.execute("""
            INSERT INTO portals (portal_key,portal_name,base_url,selector,link_tag,language)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(portal_key) DO UPDATE SET
                portal_name=excluded.portal_name, base_url=excluded.base_url,
                selector=excluded.selector, link_tag=excluded.link_tag, language=excluded.language
        """, (key, cfg["name"], cfg["url"], cfg["selector"], cfg["link_tag"], cfg["language"]))
    conn.commit()
    conn.close()


def extract_title(text):
    for line in (text or "").splitlines():
        s = line.strip()
        if s.lower().startswith("title:"):
            return s[6:].strip()
    return ""


def get_clean_article_text(url):
    if not url:
        return ""
    try:
        r = requests.get(f"https://r.jina.ai/{url}", timeout=16,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"})
        r.raise_for_status()
        return r.text.strip()
    except Exception as e:
        print(f"  Jina failed: {e}")
        return ""


def summarize_with_gemini(url, lang="en"):
    if not url:
        return "", ""
    if lang == "en":
        prompt = f'Summarize the news at this URL in English (90-110 words). Extract 5-10 keywords. Return ONLY JSON no markdown: {{"summary":"...","keywords":"kw1,kw2"}} URL: {url}'
    else:
        prompt = f'यो URL को समाचार नेपालीमा संक्षिप्त गर्नुहोस् (९०-११० शब्द)। ५-१० किवर्ड दिनुहोस्। केवल JSON फर्काउनुहोस् no markdown: {{"summary":"...","keywords":"kw1,kw2"}} URL: {url}'
    try:
        raw = client.models.generate_content(model="gemini-2.5-flash", contents=prompt).text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        s, e = raw.find("{"), raw.rfind("}") + 1
        if s == -1 or e <= s:
            return "", ""
        d = json.loads(raw[s:e])
        return d.get("summary", "").strip(), d.get("keywords", "").strip()
    except Exception as ex:
        print(f"  Gemini {lang.upper()} failed: {str(ex)[:100]}")
        return "", ""


def fix_url(href, portal_url):
    """Convert relative URLs to absolute."""
    href = (href or "").strip()
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        parsed = urlparse(portal_url)
        return f"{parsed.scheme}://{parsed.netloc}{href}"
    return ""


def scrape_portal(key, portal, conn, now, date_str, live_str):
    c = conn.cursor()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        try:
            context = browser.new_context(
                viewport={"width": 1024, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
            )
            context.route("**/*", lambda route, req:
                route.abort() if req.resource_type in ("media")
                else route.continue_())

            page = context.new_page()
            page.goto(portal["url"], wait_until="domcontentloaded", timeout=60000)

            wait_secs = 12 if key in ("onlinekhabar", "ratopati", "himalyantimes", "setopati") else 7
            time.sleep(wait_secs)

            el = page.wait_for_selector(portal["selector"], timeout=22000)
            if not el:
                print(f"{portal['name']:22} -> selector not found\n")
                return

            el.scroll_into_view_if_needed()
            filename   = f"{key}_{date_str}_{now.strftime('%H%M%S')}.png"
            thumb_path = os.path.join(THUMB_DIR, filename)
            el.screenshot(path=thumb_path)

            link_el     = el.query_selector(portal["link_tag"])
            raw_href    = link_el.get_attribute("href") if link_el else ""
            article_url = fix_url(raw_href, portal["url"])

            if not article_url:
                print(f"  Invalid URL skipped: {raw_href!r}\n")
                return

            clean_text        = get_clean_article_text(article_url)
            title             = extract_title(clean_text)
            summary_en, kw_en = summarize_with_gemini(article_url, "en")
            summary_np, kw_np = summarize_with_gemini(article_url, "np")

            c.execute("""
                INSERT INTO articles (article_url,portal_key,title,clean_content,
                    summary_en,keywords_en,summary_np,keywords_np,first_seen_date)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(article_url) DO UPDATE SET
                    title=COALESCE(NULLIF(excluded.title,''),articles.title),
                    clean_content=COALESCE(NULLIF(excluded.clean_content,''),articles.clean_content),
                    summary_en=COALESCE(NULLIF(excluded.summary_en,''),articles.summary_en),
                    keywords_en=COALESCE(NULLIF(excluded.keywords_en,''),articles.keywords_en),
                    summary_np=COALESCE(NULLIF(excluded.summary_np,''),articles.summary_np),
                    keywords_np=COALESCE(NULLIF(excluded.keywords_np,''),articles.keywords_np)
            """, (article_url, key, title, clean_text, summary_en, kw_en, summary_np, kw_np, date_str))

            article_id = c.execute(
                "SELECT article_id FROM articles WHERE article_url=?", (article_url,)
            ).fetchone()[0]

            c.execute("""
                INSERT OR IGNORE INTO headline_snapshots
                    (scrape_datetime,portal_key,article_id,thumbnail_filename,thumbnail_path)
                VALUES (?,?,?,?,?)
            """, (live_str, key, article_id, filename, thumb_path))

            c.execute("UPDATE portals SET last_scraped_at=? WHERE portal_key=?", (live_str, key))
            conn.commit()

            print(f"{portal['name']:22} | {filename}")
            print(f"URL   : {article_url[:78]}")
            print(f"Title : {(title or '(none)')[:72]}")
            print(f"EN    : {(summary_en or '(empty)')[:65]}")
            print(f"NP    : {(summary_np or '(empty)')[:65]}")
            print()

        except Exception as e:
            print(f"{portal['name']:22} -> {str(e)[:140]}\n")
        finally:
            browser.close()


def scrape_today():
    now      = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    live_str = now.isoformat(timespec="seconds")
    init_db()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    for key, portal in NEWS_PORTALS.items():
        scrape_portal(key, portal, conn, now, date_str, live_str)
        time.sleep(3)

    conn.close()
    print("Finished")


if __name__ == "__main__":
    scrape_today()
