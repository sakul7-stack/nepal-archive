import requests
import sqlite3
from datetime import datetime, timedelta
import time

conn = sqlite3.connect("wayback_nepal_news.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT,
    date TEXT,
    timestamp TEXT,
    archive_url TEXT,
    UNIQUE(site, date)
)
""")

SITES = {
    "onlinekhabar": "onlinekhabar.com",
    "setopati": "setopati.com",
    "ekantipur": "ekantipur.com",
    "ratopati": "ratopati.com",
    "nagariknews": "nagariknews.nagariknetwork.com",
    "himalkhabar": "himalkhabar.com",
    "nepalnews": "nepalnews.com",
    "myrepublica": "myrepublica.nagariknetwork.com",
    "annapurnapost": "annapurnapost.com",
    "kathmandupost": "kathmandupost.com"
}

BASE_URL = "http://web.archive.org/cdx/search/cdx"



def get_snapshots(site, date):
    """Get all snapshots for a site on a specific date"""
    params = {
        "url": site,
        "from": date,
        "to": date,
        "output": "json",
        "fl": "timestamp,original",
        "filter": "statuscode:200",
        "collapse": "timestamp:8"  
    }

    try:
        res = requests.get(BASE_URL, params=params, timeout=15)
        data = res.json()
        if len(data) > 1:
            return data[1:]  # skip header
    except Exception as e:
        print(f" Error fetching snapshots for {site} on {date}: {e}")
    
    return []

def pick_middle(snapshots):
    """Pick middle snapshot from list"""
    if not snapshots:
        return None
    return snapshots[len(snapshots)//2]

def save_to_db(site, date, timestamp, original):
    """Save snapshot to SQLite database"""
    archive_url = f"https://web.archive.org/web/{timestamp}/{original}"
    try:
        cur.execute("""
            INSERT OR IGNORE INTO snapshots (site, date, timestamp, archive_url)
            VALUES (?, ?, ?, ?)
        """, (site, date, timestamp, archive_url))
        conn.commit()
        print(f" Saved {archive_url}")
    except Exception as e:
        print(f"DB Error for {site} on {date}: {e}")


start_date = datetime(2003, 1, 1)
end_date = datetime.now()

current = start_date

while current <= end_date:
    date_str = current.strftime("%Y%m%d")      
    pretty_date = current.strftime("%Y-%m-%d") 

    print(f"\nProcessing {pretty_date}")

    for site_name, domain in SITES.items():
        print(f"   {site_name}...", end="")
        snapshots = get_snapshots(domain, date_str)

        if not snapshots:
            print("No snapshot")
            continue

        chosen = pick_middle(snapshots)
        if chosen:
            timestamp, original = chosen
            save_to_db(site_name, pretty_date, timestamp, original)

        time.sleep(1)  

    current += timedelta(days=1)

conn.close()
print("\ncompleted")
