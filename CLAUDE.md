# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repository contains Python utilities for transferring phone numbers and their dial-in configurations between Daily.co domains. This is crucial for customers migrating from DailyBots to Pipecat Cloud.

## Commands

### Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp env.example .env
# Edit .env to add your DAILY_SOURCE_API_KEY and DAILY_TARGET_API_KEY
```

### Core Workflows

1. **Create Transfer Plan** (dry-run phase):
   ```bash
   python create-transfer-plan.py
   ```

2. **Execute Transfer**:
   ```bash
   python transfer.py
   ```

3. **Add Unverified Caller IDs**:
   ```bash
   python add-unverified-callerids.py
   ```

4. **Delete Phone Numbers**:
   ```bash
   # Interactive mode with confirmations
   python delete-phone-numbers.py <DAILY_API_KEY>
   
   # Delete all without confirmation
   python delete-phone-numbers.py <DAILY_API_KEY> --delete-all
   ```

## Architecture

### Key Components

1. **create-transfer-plan.py**: Discovers phone numbers and configs, builds transfer plan
   - Fetches purchased phone numbers from source domain
   - Discovers associated pinless_dialin and pin_dialin configs
   - Handles both legacy (root domain) and modern (domain-dialin-config) configurations
   - Generates `transfer_plan.json` with all transfer details

2. **transfer.py**: Executes the transfer plan
   - Transfers phone numbers via Daily API
   - Deletes configs from source domain
   - Recreates configs in target domain
   - Supports rollback on failure

3. **delete-phone-numbers.py**: Bulk delete phone numbers from a domain
   - Lists all phone numbers with details (ID, country, provider, creation date)
   - Shows domain information
   - Filters out already deleted numbers
   - Interactive confirmation mode with double-check for safety
   - `--delete-all` flag for automated deletion without prompts
   - Provides summary of successful/failed deletions
   - Uses the `/release-phone-number/{id}` endpoint

### Critical Transfer Flow

1. **Phone Transfer**: Must happen before config deletion
2. **Config Deletion**: Must happen before config recreation (configs must be deleted from source before they can be created in target)
3. **Config Recreation**: Final step, includes rollback option on failure

### API Endpoints Used

- `GET /v1/purchased-phone-numbers` - List phone numbers
- `GET /v1/` - Get domain info and legacy configs
- `GET /v1/domain-dialin-config` - Get modern dial-in configs
- `POST /v1/transfer-phone-number/{id}` - Transfer phone number
- `DELETE /v1/domain-dialin-config/{id}` - Delete config
- `POST /v1/domain-dialin-config` - Create config
- `POST /v1/verified-caller-ids` - Add verified caller ID
- `DELETE /v1/release-phone-number/{id}` - Release (delete) phone number, it will also delete the corresponding dialin-config

### Key Data Structures

Transfer plan entry format:
```json
{
  "+1234567890": {
    "source_phone_id": "uuid",
    "src_type": "domain-dialin-config|root-pinless|root-pin",
    "config_id": "uuid",
    "config_data": {
      "phone_number": "+1234567890",
      "room_creation_api": "https://...",
      "hmac": "...",
      "name_prefix": "...",
      "type": "pinless_dialin|pin_dialin"
    }
  }
}
```

### Important Considerations

- Phone transfers disconnect active calls - ensure no calls in progress
- Configs without phone numbers (SIP-only) are prompted for optional transfer
- Configs for deleted phone numbers are separated into `orphaned_phone_configs.json`
- Script detects and prompts for correction of invalid "dailybots" room_creation_api values
- Unverified caller IDs are saved to `unverified_caller_ids.json` for manual addition
- Success/failure logs are saved to `transfer_success.json` and `transfer_failures.json`

### Orphaned Config Handling

The script distinguishes between two types of orphaned configs:
1. **SIP-only configs** (no phone_number field) - Can be optionally transferred
2. **Configs for deleted phone numbers** - Cannot be transferred, saved to `orphaned_phone_configs.json`

### Rate Limit Handling

The `transfer.py` script includes automatic retry logic with exponential backoff to handle rate limits and temporary API failures:

- Centralized HTTP request handling via `make_api_request()` function
- Automatic retry on 400/429 status codes (configurable)
- Exponential backoff with configurable delays (1s, 2s, 4s by default)
- Adds delay between phone number transfers to prevent rate limits
- Configuration via environment variables:
  - `MAX_RETRIES`: Number of retry attempts (default: 3)
  - `INITIAL_DELAY`: Initial retry delay in seconds (default: 1)
  - `BACKOFF_FACTOR`: Exponential backoff multiplier (default: 2)
  - `TRANSFER_DELAY`: Delay between transfers in seconds (default: 2)

### Known Issues Fixed

- **Rollback failures**: Now uses the new phone ID returned from transfer API for rollback operations
- **400 errors during high-volume transfers**: Automatic retry with backoff handles rate limits
- **Code maintainability**: Centralized HTTP request handling reduces code duplication
