import os
import subprocess
import sqlite3
import sys
from datetime import datetime

stations = {
    "kantipur": {
        "url": "https://radio-broadcast.ekantipur.com/stream",
        "duration_min": 30,
        "language": "nepali"
    },
    "ujalyo": {
        "url": "https://stream-146.zeno.fm/wtuvp08xq1duv",
        "duration_min": 30,
        "language": "nepali"
    },
    "radio_nepal_english": {
        "url": "https://stream1.radionepal.gov.np/live/",
        "duration_min": 20,
        "language": "english"
    },
    "bbc_nepali": {
        "url": "https://stream.live.vc.bbcmedia.co.uk/bbc_nepali_radio",
        "duration_min": 16,
        "language": "nepali"
    }
}

output_dir = "radio_recordings"
db_file = "recordings.db"

os.makedirs(output_dir, exist_ok=True)

def init_db():
    conn = sqlite3.connect(db_file)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS stations (
            station_name TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            duration_min INTEGER NOT NULL,
            language TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_name TEXT NOT NULL,
            filename TEXT NOT NULL,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            FOREIGN KEY (station_name) REFERENCES stations(station_name)
        )
    ''')
    
    
    for name, info in stations.items():
        c.execute('''
            INSERT OR IGNORE INTO stations (station_name, url, duration_min, language)
            VALUES (?, ?, ?, ?)
        ''', (name, info['url'], info['duration_min'], info['language']))

    conn.commit()
    conn.close()

def get_station_info(station_name):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute('SELECT url, duration_min, language FROM stations WHERE station_name=?', (station_name,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"url": row[0], "duration_min": row[1], "language": row[2]}
    else:
        return None

def log_recording(station_name, filename):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M:%S')
    c.execute('''
        INSERT INTO recordings (station_name, filename, date, start_time)
        VALUES (?, ?, ?, ?)
    ''', (station_name, filename, date_str, time_str))
    conn.commit()
    conn.close()
    print(f"[INFO] Logged recording in database: {filename}")

def record_station(station_name):
    info = get_station_info(station_name)
    if not info:
        print(f"[ERROR] Unknown station: {station_name}")
        sys.exit(1)

    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    filename = f"{output_dir}/{station_name}_{date_str}.mp3"

    print(f"[INFO] Recording {station_name} -> {filename} ({info['duration_min']} min, {info['language']})")

    duration_sec = info["duration_min"] * 60

    cmd = [
        "ffmpeg",
        "-y",
        "-i", info["url"],
        "-t", str(duration_sec),
        "-acodec", "libmp3lame",
        "-ab", "64k",
        filename
    ]

    subprocess.run(cmd)

    log_recording(station_name, filename)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python record_radio.py <station_name>")
        print(f"Available stations: {', '.join(stations.keys())}")
        sys.exit(1)

    init_db()
    station_name = sys.argv[1]
    record_station(station_name)
