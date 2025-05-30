import json
import os

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

DAILY_TARGET_API_KEY = os.getenv("DAILY_TARGET_API_KEY")
BASE_URL = "https://api.daily.co/v1"

if not DAILY_TARGET_API_KEY:
    raise ValueError("❌ DAILY_TARGET_API_KEY is not set. Check your .env file.")


def add_unverified_caller_ids():
    with open("unverified_caller_ids.json", "r") as f:
        caller_ids = json.load(f)
    headers = {"Authorization": f"Bearer {DAILY_TARGET_API_KEY}"}
    for entry in caller_ids:
        number = entry.get("number")
        name = entry.get("name", "")
        payload = {"number": number, "name": name}
        response = requests.post(
            f"{BASE_URL}/verified-caller-ids",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code == 200:
            print(f"✅ Added {number} ({name})")
        else:
            print(f"❌ Failed to add {number} ({name})")
            print("Status Code:", response.status_code)
            print("Response:", response.text)


if __name__ == "__main__":
    add_unverified_caller_ids()
