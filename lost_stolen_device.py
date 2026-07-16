from __future__ import annotations

import argparse
import os
import guava
from guava import Agent

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

agent = Agent(
    name="Bianca",
    organization="Metro by T-Mobile",
    purpose=(
        "Help customers report lost or stolen devices, "
        "secure their accounts and find replacement options."
    ),
)

if __name__ == "__main__":
    from guava import logging_utils
    logging_utils.configure_logging()

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--phone", action="store_true")
    group.add_argument("--webrtc", action="store_true")
    group.add_argument("--local", action="store_true")
    group.add_argument("--chat", action="store_true")
    args = parser.parse_args()

    if args.phone:
        agent.listen_phone(os.environ["GUAVA_AGENT_NUMBER"])
    elif args.webrtc:
        agent.listen_webrtc()
    elif args.chat:
        agent.chat()
    else:
        agent.call_local()