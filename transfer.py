import json as json_module
import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

success_log = []
failure_log = []

DAILY_SOURCE_API_KEY = os.getenv("DAILY_SOURCE_API_KEY")
DAILY_TARGET_API_KEY = os.getenv("DAILY_TARGET_API_KEY")
BASE_URL = "https://api.daily.co/v1"

# Retry configuration for rate limit handling
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
INITIAL_DELAY = int(os.getenv("INITIAL_DELAY", "1"))
BACKOFF_FACTOR = int(os.getenv("BACKOFF_FACTOR", "2"))
TRANSFER_DELAY = int(os.getenv("TRANSFER_DELAY", "2"))

if not DAILY_SOURCE_API_KEY or not DAILY_TARGET_API_KEY:
    raise ValueError(
        "❌ DAILY_SOURCE_API_KEY or DAILY_TARGET_API_KEY is not set. Check your .env file."
    )


def make_api_request(method, url, headers=None, json_data=None, retry_on_codes=None):
    """
    Make an API request with automatic retry on failure.
    
    Args:
        method: HTTP method ('GET', 'POST', 'DELETE')
        url: Full URL to call
        headers: Request headers
        json_data: JSON payload for POST requests
        retry_on_codes: List of status codes that should trigger a retry (default: [400, 429])
    
    Returns:
        requests.Response object
    """
    retry_on_codes = retry_on_codes or [400, 429]
    
    def _make_request():
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers)
        elif method.upper() == 'POST':
            response = requests.post(url, headers=headers, json=json_data)
        elif method.upper() == 'DELETE':
            response = requests.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        if response.status_code in retry_on_codes:
            raise Exception(f"HTTP {response.status_code} error (possibly rate limit): {response.text}")
        
        return response
    
    for attempt in range(MAX_RETRIES):
        try:
            return _make_request()
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                # Return a mock response for the last failed attempt
                class MockResponse:
                    def __init__(self, status_code, text):
                        self.status_code = status_code
                        self.text = text
                    def json(self):
                        try:
                            return json_module.loads(self.text)
                        except:
                            return {"error": self.text}
                return MockResponse(retry_on_codes[0], str(e))
            
            delay = INITIAL_DELAY * (BACKOFF_FACTOR ** attempt)
            print(f"⏳ Request failed, retrying in {delay} seconds... (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(delay)


def get_domain_name(api_key):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = make_api_request("GET", f"{BASE_URL}/", headers=headers)
    if response.status_code == 200:
        return response.json().get("domain_name")
    raise ValueError("❌ Unable to retrieve domain name from API key.")


def check_api_identity(label, token):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = make_api_request("GET", f"{BASE_URL}/", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"\n🔑 {label} domain: {data.get('domain_name')} (id: {data.get('domain_id')})")
    else:
        print(f"❌ Failed to verify {label} API token.")
        print("Status Code:", response.status_code)
        print("Response:", response.text)


def create_dialin_config(api_key, config_data):
    url = f"{BASE_URL}/domain-dialin-config"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = make_api_request("POST", url, headers=headers, json_data=config_data)
    
    if response.status_code in (200, 201):
        return response.json()
    else:
        print(f"❌ Failed to create dialin config: {response.text}")
        return None


def delete_dialin_config(api_key, config_id):
    url = f"{BASE_URL}/domain-dialin-config/{config_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    response = make_api_request("DELETE", url, headers=headers)
    
    if response.status_code in (200, 204):
        success_log.append(config_id + " [config deleted]")
        print(f"✅ Deleted dialin config ID: {config_id}")
    else:
        failure_log.append(config_id + " [config deletion failed]")
        print(f"⚠️ Failed to delete dialin config ID {config_id}: {response.text}")


def request_phone_number_transfer(phone_id, from_api_key, to_api_key):
    headers = {
        "Authorization": f"Bearer {from_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{BASE_URL}/transfer-phone-number/{phone_id}"
    payload = {
        "transferDomainName": get_domain_name(to_api_key),
        "transferDomainApi": to_api_key,
    }
    return make_api_request("POST", url, headers=headers, json_data=payload)


def transfer_number_and_config(identifier, entry, source_api_key, target_api_key):
    phone_id = entry["source_phone_id"]
    src_type = entry["src_type"]
    config_id = entry["config_id"]
    config_data = entry["config_data"]

    if not phone_id:
        print(f"ℹ️ No phone number ID for {identifier}, skipping transfer step.")
        phone_transfer_skipped = True
    else:
        phone_transfer_skipped = False

    # Step a: Transfer the number
    if not phone_transfer_skipped:
        move_resp = request_phone_number_transfer(phone_id, source_api_key, target_api_key)
        if move_resp.status_code not in (200, 201):
            failure_log.append(identifier + " [transfer failed]")
            print(f"❌ Failed to transfer {identifier}: {move_resp.text}")
            return False
        else:
            success_log.append(identifier + " [transfer successful]")
            print(f"✅ Transferred number {identifier} to target domain")

    # Step b: Delete config in source domain
    if src_type == "domain-dialin-config" and config_id:
        delete_dialin_config(source_api_key, config_id)

    # Step c: Copy config to target domain
    if config_data:
        new_config_data = config_data.copy()
        restore_config_data = config_data.copy()
        # Remove keys that are not part of the config
        for key in ["sip_uri", "target_room_creation_api", "source_room_creation_api"]:
            new_config_data.pop(key, None)
            restore_config_data.pop(key, None)

        new_config_data["room_creation_api"] = config_data.get(
            "target_room_creation_api"
        ) or config_data.get("room_creation_api")

        restore_config_data["room_creation_api"] = config_data.get(
            "source_room_creation_api"
        ) or config_data.get("room_creation_api")

        # Validate required field
        if not new_config_data.get("room_creation_api"):
            print(f"❌ Missing room_creation_api for {identifier}. Skipping.")
            failure_log.append(identifier + " [missing room_creation_api]")
            return False

        # Validate nested objects
        if "timeout_config" in new_config_data and not isinstance(
            new_config_data["timeout_config"], dict
        ):
            print(f"⚠️ Invalid timeout_config format for {identifier}. Removing.")
            new_config_data.pop("timeout_config")

        create_resp = create_dialin_config(target_api_key, new_config_data)
        if not create_resp:
            failure_log.append(identifier + " [config failed]")
            print(f"❌ Failed to create config for {identifier}")
            rollback = input("🔁 Rollback transfer? (y/n): ").strip().lower()
            if rollback == "y":
                # Rollback: move number back and restore config
                rollback_resp = request_phone_number_transfer(
                    phone_id, target_api_key, source_api_key
                )
                if rollback_resp.status_code in (200, 201):
                    success_log.append(identifier + " [rollback successful]")
                    print(f"✅ Rolled back number {identifier} to source domain")
                else:
                    failure_log.append(identifier + " [rollback failed]")
                    print(
                        f"❌ Failed to rollback {identifier}. Status: {rollback_resp.status_code}"
                    )
                    print("Response:", rollback_resp.text)
                if rollback_resp.status_code in (200, 201) and config_id:
                    create_dialin_config(source_api_key, restore_config_data)
                    success_log.append(identifier + " [config restored]")
                    print(f"✅ Restored config for {identifier} in source domain")
            return False
        success_log.append(identifier + " [config created]")

    return True


if __name__ == "__main__":
    # Step 0: Confirm if the API key is mapped to the correct source domain
    check_api_identity("Source", DAILY_SOURCE_API_KEY)
    check_api_identity("Target", DAILY_TARGET_API_KEY)

    # prompt user to confirm
    confirm = input("\n📝 Do you want to proceed with the transfer? (y/n): ").strip().lower()
    if confirm != "y":
        print("\n❌ Transfer cancelled by user.")
        exit()

    # Step 1: Load and verify transfer_plan.json
    try:
        with open("transfer_plan.json") as f:
            transfer_plan = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load transfer_plan.json: {e}")
        exit()

    if not transfer_plan:
        print("❌ transfer_plan.json is empty. Nothing to transfer.")
        exit()

    # Step 2: Process each entry in the plan
    for idx, (identifier, entry) in enumerate(transfer_plan.items()):
        print(f"\n📞 Processing {identifier}...")
        success = transfer_number_and_config(
            identifier, entry, DAILY_SOURCE_API_KEY, DAILY_TARGET_API_KEY
        )
        if not success:
            print(f"⚠️ Skipping {identifier} due to failure.")
        
        # Add a small delay between transfers to avoid rate limits
        if idx < len(transfer_plan) - 1:
            print(f"⏳ Waiting {TRANSFER_DELAY} seconds before next transfer...")
            time.sleep(TRANSFER_DELAY)

    with open("transfer_success.json", "w") as f:
        json.dump(success_log, f, indent=2)

    with open("transfer_failures.json", "w") as f:
        json.dump(failure_log, f, indent=2)

    print(f"\n✅ {len(success_log)} transfers succeeded.")
    print(f"❌ {len(failure_log)} transfers failed.")
