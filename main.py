import os
import sys
import time
import requests
import pytz
from datetime import datetime, timedelta

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

def get_fresh_token_api(email, password):
    print("🔐 Getting fresh token via API...")

    try:
        r = requests.post(
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
            json={"email": email, "password": password},
            timeout=10,
        )

        if r.status_code != 200:
            print(f"❌ Login failed: {r.status_code}")
            print(r.text)
            return None

        token = r.json().get("serial")
        if not token:
            print("❌ No token in response")
            return None

        print(f"✅ Got token: {token[:30]}...")
        telegram("🔑 Fresh token obtained")
        return token

    except Exception as e:
        print(f"❌ Token error: {e}")
        return None


def update_session_headers():
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

    print("🔐 Logging in (fresh token)...")
    token = get_fresh_token_api(EMAIL, PASSWORD)

    if not token:
        fatal("❌ Failed to obtain token")

    TOKEN = token
    update_session_headers()

    telegram("🔐 Logged in successfully")
    print("✅ Login OK")


def api_request(method, url, **kwargs):
    global TOKEN

    r = session.request(method, url, **kwargs)

    if r.status_code == 401:
        print("⚠️ 401 Unauthorized — refreshing token")
        telegram("🔄 Token expired, refreshing...")

        token = get_fresh_token_api(EMAIL, PASSWORD)
        if not token:
            raise RuntimeError("❌ Token refresh failed")

        TOKEN = token
        update_session_headers()

        r = session.request(method, url, **kwargs)
        if r.status_code == 401:
            raise RuntimeError("❌ Token still invalid after refresh")

    if r.status_code == 404:
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
        if d.weekday() in (0, 3):  # Monday & Thursday
            t = TZ.localize(datetime.combine(d, datetime.min.time())) + timedelta(seconds=1)
            if t > n:
                return t
    fatal("No trigger time found")


def sleep_until(t):
    remaining = (t - now()).total_seconds()
    print(f"⏳ Sleeping {remaining/3600:.2f}h until {t}")
    while (t - now()).total_seconds() > 0:
        time.sleep(0.5)

# ---------------- BOOKING ----------------

def get_slots(date_str):
    return api_request(
        "GET",
        f"{BASE_URL}/api/user_app/v2/activities/{ACTIVITY_ID}/admissions",
        params={"date": date_str},
    )


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
    print(f"🎯 Booking slot {slot_id}")

    if DRY_RUN:
        telegram(f"🧪 DRY RUN — slot {slot_id}")
        print("⚠️ DRY RUN — not booking")
        return True

    r = api_request(
        "POST",
        f"{BASE_URL}/api/user_app/v2/admissions/{slot_id}/tickets",
        json={}
    )

    if not r:
        telegram("❌ Booking failed")
        return False

    telegram(f"🎉 BOOKED — Ticket ID {r.get('id')}")
    print(f"🎉 Booked! Ticket ID: {r.get('id')}")
    return True

# ---------------- MAIN ----------------

if __name__ == "__main__":
    telegram("🤖 TIMP Auto-Booking Bot started")
    login()

    while True:
        trigger = next_trigger()
        target_date = (trigger + timedelta(days=DAYS_AHEAD)).strftime("%Y-%m-%d")

        print("\n" + "=" * 60)
        print(f"⏰ Trigger: {trigger}")
        print(f"🎯 Target date: {target_date}")
        print("=" * 60 + "\n")

        sleep_until(trigger)

        # 🔐 JUST-IN-TIME AUTH
        login()

        telegram(f"🚀 Booking window open for {target_date}")
        print(f"🚀 Attempting booking for {target_date}")

        start = time.time()
        booked = False

        while time.time() - start < 120:
            slots = get_slots(target_date)
            slot = find_slot(slots)

            if slot:
                telegram("✅ Slot found, booking...")
                if book(slot["id"]):
                    booked = True
                    break
                time.sleep(2)
            else:
                if int(time.time() - start) % 10 == 0:
                    print("⏳ Slot not available yet")
                time.sleep(1)

        if booked:
            telegram(f"✅ Successfully booked {target_date} at {TARGET_HOURS}")
            print("✅ Booking successful")
        else:
            telegram(f"❌ Failed to book {target_date}")
            print("❌ Booking failed")

        print("🔁 Waiting for next cycle\n")
