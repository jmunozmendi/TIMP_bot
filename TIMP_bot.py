import os

# ================= USER CONFIG =================

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

BASE_URL = os.getenv("BASE_URL")

API_ACCESS_KEY = os.getenv("API_ACCESS_KEY")
TOKEN = os.getenv("TOKEN")

TIMEZONE = os.getenv("TIMEZONE", "Europe/Madrid")

TARGET_HOURS = os.getenv("TARGET_HOURS", "17:00 - 18:00")
TARGET_PROFESSIONAL_ID = int(os.getenv("TARGET_PROFESSIONAL_ID", 44640))
ACTIVITY_ID = int(os.getenv("ACTIVITY_ID", 69123))
BRANCH_BUILDING_ID = int(os.getenv("BRANCH_BUILDING_ID", 10815))
DAYS_AHEAD = int(os.getenv("DAYS_AHEAD", 7))

DRY_RUN = os.getenv("DRY_RUN", "False").lower() == "true"
BOOK_NOW = os.getenv("BOOK_NOW", "True").lower() == "true"

# Telegram
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "True").lower() == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ================= END CONFIG =================


import requests
import time
from datetime import datetime, timedelta
import pytz
import sys
from datetime import datetime, timedelta
import pytz

def get_target_date(days_ahead: int):
    tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(tz)
    return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

TZ = pytz.timezone(TIMEZONE)

session = requests.Session()


# ---------------- ALERTS ----------------

def telegram(msg):
    if not TELEGRAM_ENABLED:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=5
        )
    except:
        pass


def fatal(msg):
    telegram(f"❌ TIMP BOT ERROR\n{msg}")
    print(msg)
    sys.exit(1)


# ---------------- AUTH ----------------
def check_token_valid():
    """Check if the current token is still valid"""
    try:
        # Make a lightweight request to test the token
        test_url = f"{BASE_URL}/api/user_app/v2/activities/{ACTIVITY_ID}/admissions"
        test_params = {"date": datetime.now(TZ).strftime("%Y-%m-%d")}
        
        r = session.request("GET", test_url, params=test_params)
        
        if r.status_code == 401:
            return False
        return True
    except:
        return False


def login():
    print("🔐 Logging in...")
    
    session.headers.update({
        "Accept": "application/timp.user-app-v2",
        "api-access-token": TOKEN,
        "api-access-key": API_ACCESS_KEY,
        "App-Platform": "web",
        "App-Version": "8.11.0",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://web.timp.pro",
        "Referer": "https://web.timp.pro/",
        "Accept-Language": "es_ES",
        "Content-Type": "application/json",
    })

    # Check if token is valid
    if not check_token_valid():
        fatal("❌ TOKEN IS INVALID! Please update TOKEN in the config and restart.")
    
    telegram("🔐 Logged in successfully")
    print("✅ Login OK")
    

def api_request(method, url, **kwargs):
    print(f"🌐 {method} {url}")
    print(f"📋 Params: {kwargs.get('params', {})}")
    print(f"🔑 Headers: {dict(session.headers)}")
    
    r = session.request(method, url, **kwargs)
    
    #print(f"📊 Status: {r.status_code}")
    #print(f"📦 Response: {r.text[:500]}")  # First 500 chars

    if r.status_code == 401:
        raise RuntimeError("❌ Token expired")

    if r.status_code == 404:
        print("⏳ Date not available yet")
        return []

    if r.status_code == 304:
        print("📦 Cached response → availability EXISTS")
        return r.json() if r.content else []

    r.raise_for_status()
    return r.json()




# ---------------- TIME ----------------

def now():
    return datetime.now(TZ)


def next_trigger():
    n = now()
    for i in range(8):
        d = (n + timedelta(days=i)).date()
        if d.weekday() in (0, 3):
            t = TZ.localize(datetime.combine(d, datetime.min.time())) + timedelta(seconds=1)
            if t > n:
                return t
    fatal("No trigger time")


def sleep_until(t):
    while (t - now()).total_seconds() > 0:
        time.sleep(0.5)


# ---------------- BOOKING ----------------

def get_slots(date_str):
    url = f"{BASE_URL}/api/user_app/v2/activities/{ACTIVITY_ID}/admissions"
    params = {
        "date": date_str
        # Remove branch_building_id from params!
    }
    return api_request("GET", url, params=params)


def find_slot(slots):
    for s in slots:
        if (
            s["status"] == "available"
            and s["hours"] == TARGET_HOURS
            and s["professional"]["id"] == TARGET_PROFESSIONAL_ID
        ):
            return s
    return None


def book(slot_id):
    print(f"🎯 Attempting to book slot ID: {slot_id}")
    print(f"🔧 DRY_RUN is set to: {DRY_RUN}")
    
    if DRY_RUN:
        telegram(f"🧪 DRY RUN booking {slot_id}")
        print("⚠️ DRY RUN mode - not actually booking")
        return

    print(f"📤 Making POST request to book...")
    
    # Correct URL structure: /admissions/{id}/tickets
    r = api_request(
        "POST",
        f"{BASE_URL}/api/user_app/v2/admissions/{slot_id}/tickets",
        json={}  # Empty body - the admission ID is in the URL
    )

    if not r or r == []:
        print("❌ Booking failed")
        telegram("❌ Booking failed")
        return False
    
    print(f"✅ Booking response: {r}")
    telegram(f"🎉 BOOKING CONFIRMED - Ticket ID: {r.get('id')}")
    print(f"🎉 Booked successfully! Ticket ID: {r.get('id')}")
    return True


# ---------------- MAIN ----------------

if __name__ == "__main__":
    login()
    telegram("🤖 TIMP Auto-Booking started")
    
    last_token_check = now()

    while True:
        # Check token every 6 hours
        if (now() - last_token_check).total_seconds() > 6 * 3600:
            print("🔍 Checking token validity...")
            if not check_token_valid():
                fatal("❌ TOKEN EXPIRED! Please get a new token and update the config.")
            print("✅ Token still valid")
            last_token_check = now()
        
        trigger = next_trigger()
        print(f"⏰ Next booking window: {trigger.strftime('%Y-%m-%d %H:%M:%S')}")
        target_date = (trigger + timedelta(days=DAYS_AHEAD)).strftime("%Y-%m-%d")
        print(f"Target date: ", target_date)
        
        sleep_until(trigger)

        # Book for 7 days from the trigger date
        target_date = (trigger + timedelta(days=DAYS_AHEAD)).strftime("%Y-%m-%d")
        telegram(f"🚀 Booking window open for {target_date}")
        print(f"🎯 Trying to book slot for {target_date}")

        start = time.time()
        booked = False

        # Try for 2 minutes
        while time.time() - start < 120:
            slots = get_slots(target_date)
            slot = find_slot(slots)

            if slot:
                print(f"✅ Found slot: {slot['hours']} with {slot['professional']['name']}")
                telegram("✅ Slot found, booking…")
                result = book(slot["id"])
                
                if result:
                    booked = True
                    break
                else:
                    print("❌ Booking failed, retrying...")
                    time.sleep(2)
            else:
                print(f"⏳ Slot not available yet, retrying... ({int(time.time() - start)}s elapsed)")
                time.sleep(1)

        if booked:
            print(f"✅ Successfully booked! Waiting for next cycle...")
        else:
            print(f"❌ Failed to book after 2 minutes")
            telegram(f"❌ Failed to book {target_date}")

        print("🔁 Waiting for next cycle (next Monday or Thursday)")

