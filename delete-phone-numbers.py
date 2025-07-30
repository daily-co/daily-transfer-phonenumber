#!/usr/bin/env python3
"""
delete-phone-numbers.py

Utility to list and bulk delete phone numbers from a Daily.co domain.
Supports interactive mode with confirmations or automatic deletion with --delete-all flag.

Usage:
    python delete-phone-numbers.py <DAILY_API_KEY>                 # Interactive mode
    python delete-phone-numbers.py <DAILY_API_KEY> --delete-all   # Delete all without confirmation
"""

import sys
import requests
import json
import argparse
from typing import List, Dict, Any

def make_api_request(method: str, url: str, headers: Dict[str, str], data: Any = None, exit_on_error: bool = True) -> requests.Response:
    """
    Make API request with error handling.
    
    Args:
        method: HTTP method (GET, DELETE)
        url: Full API endpoint URL
        headers: Request headers including authorization
        data: Optional request body data
        exit_on_error: If True, exit program on error; if False, raise exception
        
    Returns:
        Response object from the API
        
    Raises:
        RequestException: If exit_on_error is False and request fails
    """
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, json=data)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        if exit_on_error:
            print(f"API request failed: {e}")
            sys.exit(1)
        else:
            raise

def get_domain_info(api_key: str) -> Dict[str, Any]:
    """
    Get domain configuration information from Daily API.
    
    Args:
        api_key: Daily API key for authentication
        
    Returns:
        Dictionary containing domain information including domain_name and created_at
    """
    url = "https://api.daily.co/v1/"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    response = make_api_request("GET", url, headers)
    return response.json()

def list_phone_numbers(api_key: str) -> List[Dict[str, Any]]:
    """
    List all purchased phone numbers for the domain.
    
    Args:
        api_key: Daily API key for authentication
        
    Returns:
        List of phone number objects, each containing:
        - id: Unique identifier for the phone number
        - phone_number: The actual phone number
        - country: Country code
        - provider: Phone service provider
        - created_at: Creation timestamp
        - deleted: Boolean indicating if number is already deleted
    """
    url = "https://api.daily.co/v1/purchased-phone-numbers"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    response = make_api_request("GET", url, headers)
    data = response.json()
    return data.get("data", [])

def release_phone_number(api_key: str, phone_id: str) -> None:
    """
    Release (delete) a single phone number using its ID.
    
    Args:
        api_key: Daily API key for authentication
        phone_id: Unique identifier of the phone number to release
        
    Raises:
        RequestException: If the release operation fails
    """
    url = f"https://api.daily.co/v1/release-phone-number/{phone_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Don't exit on error - let caller handle individual failures
    make_api_request("DELETE", url, headers, exit_on_error=False)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Delete Daily.co phone numbers")
    parser.add_argument("api_key", help="Daily API key")
    parser.add_argument("--delete-all", action="store_true", help="Delete all phone numbers without confirmation")
    
    args = parser.parse_args()
    api_key = args.api_key
    skip_confirmation = args.delete_all
    
    # Step 1: Get and display domain information
    print("Fetching domain information...")
    domain_info = get_domain_info(api_key)
    print(f"\nDomain: {domain_info.get('domain_name', 'N/A')}")
    print("-" * 50)
    
    # Step 2: List all phone numbers
    print("\nFetching phone numbers...")
    phone_numbers = list_phone_numbers(api_key)
    
    if not phone_numbers:
        print("No phone numbers found.")
        return
    
    # Display all phone numbers with details
    print(f"\nFound {len(phone_numbers)} phone number(s):")
    print("-" * 50)
    
    for i, phone in enumerate(phone_numbers, 1):
        print(f"{i}. {phone.get('number', phone.get('phone_number', 'N/A'))}")
        print(f"   ID: {phone.get('id', 'N/A')}")
        print(f"   Country: {phone.get('country', 'N/A')}")
        print(f"   Provider: {phone.get('provider', 'N/A')}")
        print(f"   Created: {phone.get('created_date', phone.get('created_at', 'N/A'))}")
        if phone.get('deleted'):
            print(f"   Status: DELETED")
        print()
    
    # Step 3: Filter out already deleted phone numbers
    # Filter out deleted phone numbers - API might not have 'deleted' field
    active_phone_numbers = [phone for phone in phone_numbers if not phone.get('deleted', False)]
    
    if not active_phone_numbers:
        print("All phone numbers are already deleted.")
        return
    
    # Step 4: Ask for confirmation (unless --delete-all flag is used)
    if not skip_confirmation:
        print("-" * 50)
        response = input(f"\nDo you want to release ALL {len(active_phone_numbers)} active phone number(s)? (yes/no): ").strip().lower()
        
        if response != "yes":
            print("Operation cancelled.")
            return
        
        # Double confirmation for safety
        response = input(f"\nAre you ABSOLUTELY SURE? This action cannot be undone. Type 'DELETE ALL' to confirm: ").strip()
        
        if response != "DELETE ALL":
            print("Operation cancelled.")
            return
    else:
        # --delete-all flag was used, show warning but proceed
        print("-" * 50)
        print(f"\n--delete-all flag detected. Releasing ALL {len(active_phone_numbers)} active phone number(s) without confirmation.")
        print("This action cannot be undone!")
        print("-" * 50)
    
    # Step 5: Release all active phone numbers
    print("\nReleasing phone numbers...")
    success_count = 0
    failed_count = 0
    
    for phone in active_phone_numbers:
        phone_id = phone.get('id')
        phone_number = phone.get('number') or phone.get('phone_number')
        
        # Skip if no ID found (shouldn't happen, but be safe)
        if not phone_id:
            print(f"Skipping {phone_number} - no ID found")
            failed_count += 1
            continue
        
        try:
            # Attempt to release the phone number
            print(f"Releasing {phone_id} {phone_number}...", end="")
            release_phone_number(api_key, phone_id)
            print(" SUCCESS")
            success_count += 1
        except Exception as e:
            # Log failure but continue with other numbers
            print(f" FAILED: {e}")
            failed_count += 1
    
    # Step 6: Display summary
    print("\n" + "=" * 50)
    print(f"Summary:")
    print(f"  Released: {success_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Total Active: {len(active_phone_numbers)}")
    print(f"  Already Deleted: {len(phone_numbers) - len(active_phone_numbers)}")

if __name__ == "__main__":
    main()