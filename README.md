# 📦 Daily.co Phone Number Transfer Utility

## Overview

This CLI utility safely transfers purchased phone numbers and their associated `pinless_dialin` configurations from one Daily.co domain to another. Bear in mind that the transfer should be done on a day when there are no calls in progress. **As the transfer will result in call disconnects!**

---

## Goals

- [x] List purchased phone numbers for a Daily domain
- [x] Allow user to select which numbers to transfer
- [x] Discover all related configs (including legacy and unnumbered SIP interconnects)
- [x] Build a full transfer plan in a dry-run/read-only phase
- [ ] Sequentially transfer phone numbers and their configs
- [ ] Clean up old configurations only after successful migration

---

## Prerequisites

- Python 3.7+
- `pip install -r requirements.txt`
- `.env` file with `DAILY_SOURCE_API_KEY` and `DAILY_TARGET_API_KEY`

Run:

```bash
python transfer.py
```

---

## Execution Model

1. **Phase 1 — Discovery (Read-Only):**
   - Step 1: Fetch purchased phone numbers
   - Step 2: Prompt user to select numbers
   - Step 3: Discover associated `pinless_dialin` configs (including ones without phone numbers)
   - Generate a `transfer_plan` structure summarizing everything
   - Print and confirm before proceeding

2. **Phase 2 — Per-Number Transfer (Write):**
   - Step 4: For each phone number:
     - Transfer the phone number via Daily API
     - Record the new phone number ID (if provided)
     - Recreate the config in the target domain using the correct ID (if needed)
     - Delete the old config if `--cleanup` is enabled

---

## API Usage

### 🔍 List Purchased Phone Numbers

```bash
curl --request GET \
  --url 'https://api.daily.co/v1/purchased-phone-numbers' \
  --header 'Authorization: Bearer <SOURCE_API_KEY>'
```

Response:

```json
{
  "total_count": 2,
  "data": [
    {
      "id": "aa197...",
      "number": "+1234567...",
      "name": "Dr. Nemo's office"
    },{
      "id": "bas123...",
      "number": "+1987654...",
      "name": "Dr. Smith's office"
    }
  ]
}
```

### 🔍 List Pinless Dial-in Configs

(a) Domain-level (legacy)

```bash
curl --request GET \
  --url 'https://api.daily.co/v1/' \
  --header 'Authorization: Bearer <SOURCE_API_KEY>'
```

Response, look inside: `config.pinless_dialin`

```json
{
  "id": "8505...",
  "config": {
    "pinless_dialin": [{
            "phone_number": "...",
            "sip_uri": "...",
            "hmac": "...",
            "room_creation_api": "...",
            "name_prefix": "..."
        }, {
            "sip_uri": "...",
            "hmac": "...",
            "room_creation_api": "...",
            "name_prefix": "..."
        }   
    ]
  }
}
```

(b) Dialin Config API (modern)


```bash
curl --request GET \
  --url 'https://api.daily.co/v1/domain-dialin-config' \
  --header 'Authorization: Bearer <SOURCE_API_KEY>'
```

Response:

```json
{
  "id": "8505...",
  "config": {
    "phone_number": "+1234567...",
    "room_creation_api": "...",
    "name_prefix": "...",
    "hmac": "..."
  }
}   
```

### 📤 Transfer Phone Number

```bash
curl --request POST \
  --url 'https://api.daily.co/v1/transfer-phone-number/<PHONE_ID>' \
  --header 'Authorization: Bearer <SOURCE_API_KEY>' \
  --header 'Content-Type: application/json' \
  --data '{
    "transferDomainName": "<TARGET_DOMAIN_NAME>",
    "transferDomainApi": "<TARGET_API_KEY>"
  }'
```

Response:

```json
{
  "status": true,
  "newId": "cb44528c-..."  
  // Optional: may be null if transfer succeeded but re-indexing failed
}
``` 

### Recreate dialin-config on target domain

Note: the config on the old domain needs to be deleted before the configs can be made on the new domain. However, the configs on the old domain need to be deleted only after the phone numbers have been transferred.

```bash
curl --request POST \
  --url 'https://api.daily.co/v1/domain-dialin-config' \
  --header 'Authorization: Bearer <TARGET_API_KEY>' \
  --header 'Content-Type: application/json' \
  --data '{
    "type": "pinless_dialin",
    "config": {
      "phone_number": "+1234567...",
      "room_creation_api": "...",
      "name_prefix": "...",
      "hmac": "...",
      "timeout_config": {
        "message": "No agent is available"
      }
    }
  }'        
  ```

  Note: Configs without phone numbers should also be migrated using this endpoint, omitting the `phone_number` field.
