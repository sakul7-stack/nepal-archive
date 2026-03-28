#!/bin/bash

cd /media/kushal/PENDRIVE/news || exit 1
source /media/kushal/PENDRIVE/news/env/bin/activate || exit 1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting paper_scraper.py" >> /home/kushal/scraper.log
python paper_scraper.py >> /home/kushal/scraper.log 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] paper_scraper.py finished (exit code $?)" >> /home/kushal/scraper.log

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting portal_scraper.py" >> /home/kushal/scraper.log
python portal_scraper.py >> /home/kushal/scraper.log 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] portal_scraper.py finished (exit code $?)" >> /home/kushal/scraper.log

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting social_scraper.py" >> /home/kushal/scraper.log
python social_scraper.py >> /home/kushal/scraper.log 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] social_scraper.py finished (exit code $?)" >> /home/kushal/scraper.log

echo "----------------------------------------" >> /home/kushal/scraper.log
