import sqlite3
import os
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import json


SCRIPT_PARENT = Path(__file__).resolve().parent
DATA_FOLDER   = SCRIPT_PARENT / "social_archive"
DATA_FOLDER.mkdir(exist_ok=True)

DB_PATH      = DATA_FOLDER / "social_archive.db"
THUMB_FOLDER = DATA_FOLDER / "thumbnails"
THUMB_FOLDER.mkdir(exist_ok=True)

TODAY_STR = datetime.now().strftime("%Y_%m_%d") 
TODAY_DB  = TODAY_STR.replace("_", "-")         

SUBREDDITS = ["IOENepal", "Nepal", "NepalSocial"]


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS platforms (
            platform_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            platform_name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS archive_dates (
            archive_date_id INTEGER PRIMARY KEY AUTOINCREMENT,
            archive_date    TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS social_posts (
            post_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            platform_id     INTEGER NOT NULL REFERENCES platforms(platform_id),
            archive_date_id INTEGER NOT NULL REFERENCES archive_dates(archive_date_id),
            title           TEXT,
            link            TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(platform_id, archive_date_id, link)
        );

        CREATE TABLE IF NOT EXISTS media_files (
            media_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id   INTEGER NOT NULL REFERENCES social_posts(post_id),
            file_path TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def get_or_create_platform(conn, platform_name):
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO platforms (platform_name) VALUES (?)", (platform_name,))
    conn.commit()
    c.execute("SELECT platform_id FROM platforms WHERE platform_name = ?", (platform_name,))
    return c.fetchone()[0]


def get_or_create_date(conn, date_str):
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO archive_dates (archive_date) VALUES (?)", (date_str,))
    conn.commit()
    c.execute("SELECT archive_date_id FROM archive_dates WHERE archive_date = ?", (date_str,))
    return c.fetchone()[0]


def insert_post(conn, platform_name, title, link, file_path=None):
    if not link:
        return
    c            = conn.cursor()
    platform_id  = get_or_create_platform(conn, platform_name)
    date_id      = get_or_create_date(conn, TODAY_DB)

    try:
        c.execute("""
            INSERT OR IGNORE INTO social_posts (platform_id, archive_date_id, title, link)
            VALUES (?, ?, ?, ?)
        """, (platform_id, date_id, title, link))
        conn.commit()
        post_id = c.lastrowid

        # If INSERT was ignored (duplicate), fetch the existing post_id
        if post_id == 0:
            c.execute("""
                SELECT post_id FROM social_posts
                WHERE platform_id = ? AND archive_date_id = ? AND link = ?
            """, (platform_id, date_id, link))
            row = c.fetchone()
            post_id = row[0] if row else None

        if post_id and file_path:
            c.execute("""
                INSERT INTO media_files (post_id, file_path) VALUES (?, ?)
            """, (post_id, str(file_path)))
            conn.commit()
    except sqlite3.Error as e:
        print(f"error: {e}")


def scrape_youtube_trending_nepal(conn):
    url = "https://yt-trends.iamrohit.in/Nepal"
    try:
        r = requests.get(url, verify=False, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        for row in soup.find_all("div", class_="row shadow-box"):
            cell = row.find("div", class_="col-md-4")
            if not cell:
                continue

            a = cell.find("a", href=True)
            if not a or "youtube.com" not in a["href"]:
                continue

            video_url = a["href"]
            img       = a.find("img")
            if not img:
                continue

            title   = img.get("title", "(title missing)")
            img_url = img["src"]

            filename = f"{TODAY_STR}_youtube.png"
            savepath = THUMB_FOLDER / filename

            try:
                img_data = requests.get(img_url, timeout=10).content
                savepath.write_bytes(img_data)
                print(f"Thumbnail saved ")
            except Exception as e:
                print(f"Thumbnail failed: {e}")
                savepath = None

            insert_post(conn, "YouTube Nepal Trending", title, video_url, savepath)
            break  # top 1 only

    except Exception as e:
        print(f"YouTube failed: {e}")


def scrape_reddit_top_posts(conn):
    cookies_file = SCRIPT_PARENT / "reddit_cookies.json"
    with open(cookies_file, encoding="utf-8") as f:
        cookies_list = json.load(f)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox",
            "--disable-gpu",
            "--mute-audio",
        ])
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        page.route("**/*", lambda route, request:
            route.abort() if request.resource_type == "font" else route.continue_())

        page.goto("https://www.reddit.com", wait_until="domcontentloaded", timeout=45000)
        context.add_cookies([
            {
                "name":     c["name"],
                "value":    c["value"],
                "domain":   c["domain"],
                "path":     c.get("path", "/"),
                "secure":   c.get("secure", False),
                "httpOnly": c.get("httpOnly", False),
            }
            for c in cookies_list
        ])

        BASE = "https://www.reddit.com"

        for subreddit in SUBREDDITS:
            print(f"\n{subreddit}")
            try:
                page.goto(f"{BASE}/r/{subreddit}/top/",
                          wait_until="domcontentloaded", timeout=60000)
                article = page.wait_for_selector("article", timeout=30000)
                if not article:
                    continue

                article.scroll_into_view_if_needed()
                bbox = article.bounding_box()
                if not bbox:
                    continue

                filename = f"{TODAY_STR}_{subreddit.lower()}.png"
                savepath = THUMB_FOLDER / filename

                page.screenshot(
                    path=str(savepath),
                    clip=bbox,
                    animations="disabled",
                    timeout=45000,
                )
                print(f" Screenshot saved")

                title     = article.get_attribute("aria-label") or "(no title)"
                link_elem = article.query_selector("a")
                post_url  = ""
                if link_elem:
                    href = link_elem.get_attribute("href")
                    if href:
                        post_url = href if href.startswith("http") else BASE + href

                insert_post(conn, f"r/{subreddit}", title, post_url, savepath)

            except Exception as e:
                print(f"error: {e}")
        browser.close()

if __name__ == "__main__":
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    scrape_youtube_trending_nepal(conn)
    scrape_reddit_top_posts(conn)
    conn.close()
