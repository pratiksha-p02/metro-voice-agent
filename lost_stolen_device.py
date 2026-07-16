from __future__ import annotations

import argparse
import os

# Temporary mock customer database
CUSTOMERS = {
    "+15551234567": {
        "name": "Jordan Alvarez",
        "pin": "4821",
        "account_type": "multi_line",
    },
    "+15552223333": {
        "name": "Priya Natarajan",
        "pin": "0099",
        "account_type": "single_line",
    },
}

def lookup_customer(phone_number: str, pin: str):
    """
    Temporary customer verification.
    Later this will query Google Sheets.
    """
    customer = CUSTOMERS.get(phone_number)
    if customer and customer["pin"] == pin:
        return customer
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--phone", action="store_true")
    group.add_argument("--webrtc", action="store_true")
    group.add_argument("--local", action="store_true")
    group.add_argument("--chat", action="store_true")
    args = parser.parse_args()

    if args.phone:
        print("Listening on phone...")
    elif args.webrtc:
        print("Listening on WebRTC...")
    elif args.chat:
        print("Starting chat...")
    else:
        print("Starting local call...")