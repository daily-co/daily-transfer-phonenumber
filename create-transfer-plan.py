import json
import os

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

DAILY_SOURCE_API_KEY = os.getenv("DAILY_SOURCE_API_KEY")
DAILY_TARGET_API_KEY = os.getenv("DAILY_TARGET_API_KEY")
BASE_URL = "https://api.daily.co/v1"

if not DAILY_SOURCE_API_KEY or not DAILY_TARGET_API_KEY:
    raise ValueError(
        "❌ DAILY_SOURCE_API_KEY or DAILY_TARGET_API_KEY is not set. Check your .env file."
    )


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
    root_pinless_configs = []
    root_pin_configs = []
    if root_resp.status_code == 200:
        root_data = root_resp.json()
        root_pinless_configs = root_data.get("config", {}).get("pinless_dialin") or []
        root_pin_configs = root_data.get("config", {}).get("pin_dialin") or []
        print(
            f"✅ Found {len(root_pinless_configs)} 'pinless_dialin' configs in root domain config"
        )
        print(f"✅ Found {len(root_pin_configs)} 'pin_dialin' configs in root domain config")
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

    if root_pinless_configs:
        print("\n📎 Root pinless_dialin configs:")
        for cfg in root_pinless_configs:
            print(json.dumps(cfg, indent=2))
    if root_pin_configs:
        print("\n📎 Root pin_dialin configs:")
        for cfg in root_pin_configs:
            print(json.dumps(cfg, indent=2))

    if dialin_configs:
        print("\n📎 Domain-dialin-config entries:")
        for cfg in dialin_configs:
            print(json.dumps(cfg, indent=2))

    return root_pinless_configs, root_pin_configs, dialin_configs


def build_transfer_plan(selected_numbers, root_pinless_configs, root_pin_configs, dialin_configs):
    # 1. Consolidate configs with dialin_config taking precedence
    config_map = {}

    for cfg in root_pinless_configs:
        key = cfg.get("phone_number") or cfg.get("sip_uri")
        if key:
            config_map[key] = {"src_type": "root-pinless", "config": cfg, "id": None}
            config_map[key]["config"]["type"] = "pinless_dialin"

    for cfg in root_pin_configs:
        key = cfg.get("phone_number") or cfg.get("sip_uri")
        if key:
            config_map[key] = {"src_type": "root-pin", "config": cfg, "id": None}
            config_map[key]["config"]["type"] = "pin_dialin"

    for cfg in dialin_configs:
        key = cfg.get("config", {}).get("phone_number") or cfg.get("config", {}).get("sip_uri")
        if key:
            config_map[key] = {
                "src_type": "domain-dialin-config",
                "config": cfg["config"],
                "id": cfg.get("id"),
            }
            config_map[key]["config"]["type"] = cfg.get("type")

    # 2. Add selected numbers to plan
    plan = {}
    skipped = {}

    for num in selected_numbers:
        number = num["number"]
        phone_id = num.get("id")
        if not phone_id:
            skipped[number] = num.get("name", "")
            continue
        entry = config_map.get(number)
        plan[number] = {
            "source_phone_id": phone_id,
            "src_type": entry["src_type"] if entry else None,
            "config_id": entry["id"] if entry else None,
            "config_data": entry["config"] if entry else None,
        }

    # 3. Prompt user about orphaned configs with no phone_number
    orphaned = []
    for key, entry in config_map.items():
        if key not in plan and entry["config"].get("phone_number") is None:
            orphaned.append((key, entry))

    if orphaned:
        print("\n📎 Found configs with no phone_number:")
        for idx, (key, entry) in enumerate(orphaned):
            print(f"[{idx}] {key} from {entry['src_type']}")
        include = (
            input("❓ Do you want to include any of these configs in the transfer plan? (y/n): ")
            .strip()
            .lower()
        )
        if include == "y":
            choice = input("❓ Transfer all configs with no phone_number? (y/n): ").strip().lower()
            if choice == "y":
                selected_indices = list(range(len(orphaned)))
            else:
                indices_input = input(
                    "Enter comma-separated list of indexes to transfer (e.g. 0,2): "
                )
                try:
                    selected_indices = [int(i.strip()) for i in indices_input.split(",")]
                except ValueError:
                    print("⚠️ Invalid input. Skipping all orphaned configs.")
                    selected_indices = []
            for idx in selected_indices:
                if 0 <= idx < len(orphaned):
                    key, entry = orphaned[idx]
                    config_copy = entry["config"].copy()
                    if config_copy.get("phone_number") is None:
                        config_copy.pop("phone_number", None)
                    plan[key] = {
                        "source_phone_id": None,
                        "src_type": entry["src_type"],
                        "config_id": entry["id"],
                        "config_data": config_copy,
                    }

    if skipped:
        print("\n⏭️ Skipped Numbers (may need to be manually added to verified-caller-ids):")
        print(json.dumps(skipped, indent=2))
        print("\n💾 Writing skipped numbers to unverified_caller_ids.json...")
        with open("unverified_caller_ids.json", "w") as f:
            json.dump(
                [{"number": number, "name": name} for number, name in skipped.items()],
                f,
                indent=2,
            )

    # Check for known invalid config values and prompt user for correction
    needs_correction = [
        key
        for key, entry in plan.items()
        if entry["config_data"] and entry["config_data"].get("room_creation_api") == "dailybots"
    ]
    if needs_correction:
        print("\n⚠️ Detected 'dailybots' as room_creation_api in the following entries:")
        for key in needs_correction:
            print(f" - {key}")
        new_value = input("🔧 Enter replacement for 'dailybots' in room_creation_api: ").strip()
        for key in needs_correction:
            plan[key]["config_data"]["source_room_creation_api"] = "dailybots"
            plan[key]["config_data"]["target_room_creation_api"] = new_value
            plan[key]["config_data"]["room_creation_api"] = new_value

    print("\n📦 Transfer Plan Summary:")
    print(json.dumps(plan, indent=2))
    return plan, skipped


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
        root_pinless_configs, root_pin_configs, dialin_configs = get_dialin_configs()
        transfer_plan, skipped_numbers = build_transfer_plan(
            selected_numbers, root_pinless_configs, root_pin_configs, dialin_configs
        )

        # Step 4: Write transfer plan to file
        with open("transfer_plan.json", "w") as f:
            json.dump(transfer_plan, f, indent=2)
        print("\n📝 transfer_plan.json has been saved.")
    else:
        print("❌ No purchased phone numbers found.")
