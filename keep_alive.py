"""
keep_alive.py — KPR Lab CRM
=============================
Render app ని sleep కాకుండా చేస్తుంది.
PC1 లో background లో run చేయండి.

start_server.bat లో add చేయండి:
  start "KPR Keep Alive" /min cmd /c "python keep_alive.py"
"""

import urllib.request
import time
import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# మీ Render app URL ఇక్కడ పెట్టండి
RENDER_URL = os.getenv("RENDER_URL", "https://kpr-lab-crm.onrender.com")
PING_INTERVAL = 8 * 60  # 8 minutes కి ఒకసారి ping

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] KEEP-ALIVE: {msg}")

def ping():
    try:
        url = f"{RENDER_URL}/health"
        req = urllib.request.Request(url, headers={"User-Agent": "KPR-KeepAlive/1.0"})
        with urllib.request.urlopen(req, timeout=15) as res:
            if res.status == 200:
                log(f"✅ Render app awake! ({RENDER_URL})")
                return True
    except Exception as e:
        log(f"⚠️ Ping failed: {e}")
    return False

def main():
    log(f"🚀 Keep-Alive started → {RENDER_URL}")
    log(f"   Ping interval: {PING_INTERVAL//60} minutes")
    log(f"   Press Ctrl+C to stop")

    # మొదటి ping వెంటనే
    ping()

    while True:
        try:
            time.sleep(PING_INTERVAL)
            ping()
        except KeyboardInterrupt:
            log("Stopped.")
            break

if __name__ == "__main__":
    main()
