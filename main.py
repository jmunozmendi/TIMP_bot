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

TZ = pytz.timezone(TIMEZONE)
session = requests.Session()

# Global token expiration tracking
token_expires_at = None


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
        test_url = f"{BASE_URL}/api/user_app/v2/activities/{ACTIVITY_ID}/admissions"
        test_params = {"date": datetime.now(TZ).strftime("%Y-%m-%d")}
        
        r = session.request("GET", test_url, params=test_params)
        
        if r.status_code == 401:
            return False
        return True
    except:
        return False


def get_fresh_token_api(email, password):
    """Get a fresh token using the API login endpoint"""
    global token_expires_at
    
    print("🔐 Getting fresh token via API...")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/user_app/v2/sessions",
            headers={
                "Accept": "application/timp.user-app-v2",
                "api-access-key": API_ACCESS_KEY,
                "App-Platform": "web",
                "App-Version": "8.11.0",
                "Content-Type": "application/json",
                "Origin": "https://web.timp.pro",
                "Referer": "https://web.timp.pro/",
            },
            json={
                "email": email,
                "password": password
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('serial')
            
            if token:
                expires_str = data.get('expires_at')
                if expires_str:
                    # Parse expiration date
                    token_expires_at = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
                    print(f"✅ Got token: {token[:30]}...")
                    print(f"⏰ Expires at: {expires_str}")
                    telegram(f"🔑 New token obtained, expires {expires_str}")
                return token
            else:
                print(f"❌ Token not found in response")
                return None
        else:
            print(f"❌ Login failed with status {response.status_code}")
            print(f"Response: {response.text}")
            telegram(f"❌ Failed to get fresh token: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Error getting token: {e}")
        telegram(f"❌ Error getting token: {e}")
        return None


def refresh_token_if_needed(target_date):
    """Refresh token if it will expire before the target booking date"""
    global TOKEN, token_expires_at
    
    if not token_expires_at:
        print("⚠️ Token expiration unknown, refreshing to be safe...")
        fresh_token = get_fresh_token_api(EMAIL, PASSWORD)
        if fresh_token:
            TOKEN = fresh_token
            update_session_headers()
        return
    
    # Parse target date and add buffer time (1 hour for the booking window)
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    target_dt = TZ.localize(target_dt) + timedelta(hours=1)
    
    # If token expires before target date, refresh it
    if token_expires_at <= target_dt:
        print(f"🔄 Token expires {token_expires_at}, but booking is on {target_dt}")
        print("🔄 Refreshing token preemptively...")
        telegram(f"🔄 Refreshing token (expires before booking date)")
        
        fresh_token = get_fresh_token_api(EMAIL, PASSWORD)
        if fresh_token:
            TOKEN = fresh_token
            update_session_headers()
            print("✅ Token refreshed successfully")
        else:
            fatal("❌ Failed to refresh token before booking!")
    else:
        print(f"✅ Token valid until {token_expires_at}, booking on {target_dt}")


def update_session_headers():
    """Update session headers with current token"""
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


def login():
    global TOKEN
    
    print("🔐 Logging in...")
    
    # Try to get a fresh token
    fresh_token = get_fresh_token_api(EMAIL, PASSWORD)
    if fresh_token:
        TOKEN = fresh_token
        print(f"✅ Using fresh token")
    else:
        print(f"⚠️ Could not get fresh token, using existing one")
    
    update_session_headers()

    if not check_token_valid():
        fatal("❌ TOKEN IS INVALID!")
    
    telegram("🔐 Logged in successfully")
    print("✅ Login OK")


def api_request(method, url, **kwargs):
    r = session.request(method, url, **kwargs)

    if r.status_code == 401:
        print("❌ 401 Unauthorized - Token may be expired")
        telegram("⚠️ Token expired during request, attempting refresh...")
        
        # Try to refresh token
        global TOKEN
        fresh_token = get_fresh_token_api(EMAIL, PASSWORD)
        if fresh_token:
            TOKEN = fresh_token
            update_session_headers()
            # Retry the request
            r = session.request(method, url, **kwargs)
            if r.status_code == 401:
                raise RuntimeError("❌ Token still invalid after refresh")
        else:
            raise RuntimeError("❌ Token expired and refresh failed")

    if r.status_code == 404:
        print("⏳ Date not available yet (404)")
        return []

    if r.status_code == 304:
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
        if d.weekday() in (0, 3):  # Monday (0) and Thursday (3)
            t = TZ.localize(datetime.combine(d, datetime.min.time())) + timedelta(seconds=1)
            if t > n:
                return t
    fatal("No trigger time")


def sleep_until(t):
    remaining = (t - now()).total_seconds()
    print(f"⏳ Sleeping for {remaining/3600:.2f} hours until {t.strftime('%Y-%m-%d %H:%M:%S')}")
    
    while (t - now()).total_seconds() > 0:
        time.sleep(0.5)


# ---------------- BOOKING ----------------

def get_slots(date_str):
    url = f"{BASE_URL}/api/user_app/v2/activities/{ACTIVITY_ID}/admissions"
    params = {"date": date_str}
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
    
    if DRY_RUN:
        telegram(f"🧪 DRY RUN booking {slot_id}")
        print("⚠️ DRY RUN mode - not actually booking")
        return True

    print(f"📤 Making POST request to book...")
    
    r = api_request(
        "POST",
        f"{BASE_URL}/api/user_app/v2/admissions/{slot_id}/tickets",
        json={}
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
    telegram("🤖 TIMP Auto-Booking Bot started")

    while True:
        trigger = next_trigger()
        target_date = (trigger + timedelta(days=DAYS_AHEAD)).strftime("%Y-%m-%d")
        
        print(f"\n{'='*60}")
        print(f"⏰ Next booking window: {trigger.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🎯 Target booking date: {target_date}")
        print(f"{'='*60}\n")
        
        # Check if token needs refresh before target date
        refresh_token_if_needed(target_date)
        
        sleep_until(trigger)

        telegram(f"🚀 Booking window open for {target_date}")
        print(f"🎯 Starting booking attempt for {target_date}")

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
                elapsed = int(time.time() - start)
                if elapsed % 10 == 0:  # Print every 10 seconds
                    print(f"⏳ Slot not available yet ({elapsed}s elapsed)")
                time.sleep(1)

        if booked:
            print(f"✅ Successfully booked! Waiting for next cycle...")
            telegram(f"✅ Successfully booked {target_date} at {TARGET_HOURS}")
        else:
            print(f"❌ Failed to book after 2 minutes")
            telegram(f"❌ Failed to book {target_date} - slot may not have opened")

        print("🔁 Waiting for next cycle (next Monday or Thursday)\n")

