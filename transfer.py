import json
import os

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

DAILY_SOURCE_API_KEY = os.getenv("DAILY_SOURCE_API_KEY")
DAILY_TARGET_API_KEY = os.getenv("DAILY_TARGET_API_KEY")
BASE_URL = "https://api.daily.co/v1"

if not DAILY_SOURCE_API_KEY:
    raise ValueError("❌ DAILY_SOURCE_API_KEY is not set. Check your .env file.")


def check_api_identity(label, token):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.get(BASE_URL + "/", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"\n🔑 {label} domain: {data.get('domain_name')} (id: {data.get('domain_id')})")
    else:
        print(f"❌ Failed to verify {label} API token.")
        print("Status Code:", response.status_code)
        print("Response:", response.text)


def get_purchased_phone_numbers():
    headers = {"Authorization": f"Bearer {DAILY_SOURCE_API_KEY}"}
    response = requests.get(f"{BASE_URL}/purchased-phone-numbers", headers=headers)

    if response.status_code != 200:
        print("Failed to fetch purchased phone numbers.")
        print("Status Code:", response.status_code)
        print("Response:", response.text)
        return []

    data = response.json()
    numbers = data.get("data", [])
    return numbers


def print_numbers(numbers):
    print("\n📞 Purchased Phone Numbers:")
    for idx, num in enumerate(numbers):
        print(f"[{idx}] {num['number']} — ID: {num['id']} — Name: {num['name']}")


# Prompt user to select numbers for transfer
def prompt_user_selection(numbers):
    while True:
        choice = input("\nDo you want to transfer all numbers? (y/n): ").strip().lower()
        if choice == "y":
            return numbers
        elif choice == "n":
            indices = input("Enter comma-separated list of indexes to transfer (e.g. 0,2): ")
            try:
                selected_indices = [int(i.strip()) for i in indices.split(",")]
                selected = [numbers[i] for i in selected_indices if 0 <= i < len(numbers)]
                if not selected:
                    print("No valid indexes selected. Try again.")
                    continue
                return selected
            except ValueError:
                print("Invalid input. Please enter numeric indexes.")
        else:
            print("Please enter 'y' or 'n'.")


# Fetch configs from both root and domain-dialin-config endpoints
def get_dialin_configs():
    headers = {"Authorization": f"Bearer {DAILY_SOURCE_API_KEY}"}

    # Fetch from root config
    root_resp = requests.get(f"{BASE_URL}/", headers=headers)
    root_configs = []
    if root_resp.status_code == 200:
        root_data = root_resp.json()
        root_configs = root_data.get("config", {}).get("pinless_dialin", [])
        print(f"✅ Found {len(root_configs)} configs in root pinless_dialin")
    else:
        print("⚠️ Failed to fetch root domain config:", root_resp.text)

    # Fetch from domain-dialin-config
    dialin_resp = requests.get(f"{BASE_URL}/domain-dialin-config", headers=headers)
    dialin_configs = []
    if dialin_resp.status_code == 200:
        dialin_data = dialin_resp.json()
        dialin_configs = dialin_data.get("data", [])
        print(f"✅ Found {len(dialin_configs)} configs in domain-dialin-config")
    else:
        print("⚠️ Failed to fetch domain-dialin-config:", dialin_resp.text)

    if root_configs:
        print("\n📎 Root pinless_dialin configs:")
        for cfg in root_configs:
            print(json.dumps(cfg, indent=2))

    if dialin_configs:
        print("\n📎 Domain-dialin-config entries:")
        for cfg in dialin_configs:
            print(json.dumps(cfg, indent=2))

    return root_configs, dialin_configs


def build_transfer_plan(selected_numbers, root_configs, dialin_configs):
    plan = {}
    skipped_numbers = {}

    for num in selected_numbers:
        phone_number = num["number"]
        phone_id = num.get("id")

        if not phone_id:
            skipped_numbers[phone_number] = num.get("name", "")
            continue

        match = None
        match_type = None
        match_id = None

        # Try to match in domain-dialin-configs first
        for cfg in dialin_configs:
            cfg_number = cfg.get("config", {}).get("phone_number")
            if cfg_number == phone_number:
                match = cfg["config"]
                match_type = "domain-dialin-config"
                match_id = cfg["id"]
                break

        # Fallback to root configs
        if not match:
            for cfg in root_configs:
                if cfg.get("sip_uri", "").find(phone_id[:6]) != -1:
                    match = cfg
                    match_type = "root"
                    break

        plan[phone_number] = {
            "source_phone_id": phone_id,
            "config_type": match_type,
            "config_id": match_id,
            "config_data": match,
        }

    if skipped_numbers:
        print("\n⏭️ Skipped Numbers (may need to be manually added to verified-caller-ids):")
        print(json.dumps(skipped_numbers, indent=2))
        print("\n💾 Writing skipped numbers to unverified_caller_ids.json...")
        with open("unverified_caller_ids.json", "w") as f:
            json.dump(
                [{"number": number, "name": name} for number, name in skipped_numbers.items()],
                f,
                indent=2,
            )

    print("\n📦 Transfer Plan Summary:")
    print(json.dumps(plan, indent=2))
    return plan, skipped_numbers


if __name__ == "__main__":
    # Step 0: Confirm if the API key is mapped to the correct source domain
    check_api_identity("Source", DAILY_SOURCE_API_KEY)
    check_api_identity("Target", DAILY_TARGET_API_KEY)

    # prompt user to confirm
    confirm = input("\n📝 Do you want to proceed with the transfer? (y/n): ").strip().lower()
    if confirm != "y":
        print("\n❌ Transfer cancelled by user.")
        exit()

    # Step 1: Fetch purchased phone numbers
    numbers = get_purchased_phone_numbers()
    if numbers:
        print_numbers(numbers)

        # Step 2: Prompt user to select numbers for transfer
        selected_numbers = prompt_user_selection(numbers)
        # print("\n Selected numbers for transfer:")
        # print_numbers(selected_numbers)

        # Step 3: Fetch configs from both endpoints for discovery
        root_configs, dialin_configs = get_dialin_configs()
        transfer_plan, skipped_numbers = build_transfer_plan(
            selected_numbers, root_configs, dialin_configs
        )
    else:
        print("❌ No purchased phone numbers found.")
