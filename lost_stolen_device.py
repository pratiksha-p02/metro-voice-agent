from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from typing import Any

import guava
from guava import Agent
logger = logging.getLogger("metro.lost_stolen_device")

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

def lookup_customer(phone_number: str, pin: str) -> dict[str, Any] | None:
    """MOCK: verify phone + PIN against the customer data source."""
    record = CUSTOMERS.get(_normalize_phone(phone_number))
    if record and record["pin"] == pin:
        return record
    return None

def suspend_line(phone_number: str) -> bool:
    """MOCK: call the account-management API to suspend the line."""
    return True

def _normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits

# ---------------------------------------------------------------------------
# Per-call state management
# ---------------------------------------------------------------------------

@dataclass
class CallState:
    authenticated: bool = False
    customer: dict[str, Any] | None = None
    phone_number: str | None = None
    auth_attempts: int = 0
    actions_taken: list[str] = field(default_factory=list)

_CALL_STATE: dict[str, CallState] = {}

def state_for(call: guava.Call) -> CallState:
    return _CALL_STATE.setdefault(call.id, CallState())




agent = Agent(
    name="Bianca",
    organization="Metro by T-Mobile",
    purpose=(
        "Help callers secure their account after a lost or stolen device, "
        "verify their identity, suspend the affected line, and guide them "
        "through replacement options."
    ),
)
@agent.on_call_start
def on_call_start(call: guava.Call) -> None:
    state_for(call)  # initialize state tracking block
    call.set_task(
        "authenticate",
        objective=(
            "You are helping a caller who may need to report a lost or stolen "
            "device. Before doing anything else, confirm that's why they're "
            "calling, then verify their identity by collecting the phone number "
            "on the account and their account PIN."
        ),
        checklist=[
            guava.Field(key="phone_number", description="The phone number associated with the account"),
            guava.Field(key="account_pin", description="The caller's account PIN"),
        ],
    )

@agent.on_task_complete("authenticate")
def on_authenticate_done(call: guava.Call) -> None:
    st = state_for(call)
    phone_number = str(call.get_field("phone_number"))
    pin = str(call.get_field("account_pin"))

    record = lookup_customer(phone_number, pin)
    st.auth_attempts += 1

    if record is None:
        call.send_instruction(
            "The phone number and PIN did not match our records. Apologize, "
            "let the caller know you'll try again, and ask them to re-confirm "
            "both the phone number and PIN."
        )
        call.set_task(
            "authenticate",
            objective="Re-collect the phone number and PIN for verification.",
            checklist=[
                guava.Field(key="phone_number", description="The phone number associated with the account"),
                guava.Field(key="account_pin", description="The caller's account PIN"),
            ],
        )
        return

    st.phone_number = _normalize_phone(phone_number)
    st.customer = record
    st.authenticated = True

    call.send_instruction(
        f"The caller is verified as {record['name']}. Greet them by name and "
        f"let them know you can help secure their account now."
    )
    call.set_task(
        "lost_or_stolen",
        objective=(
            "Confirm whether the device was lost or stolen, explain that you're "
            "about to temporarily suspend the line to protect the account, and "
            "get the caller's confirmation before doing so."
        ),
        checklist=[
            guava.Field(
                key="device_status",
                description="Was the device lost or stolen?",
                field_type="multiple_choice",
                choices=["lost", "stolen"],
            ),
            guava.Field(
                key="suspend_confirmed",
                description="Did the caller confirm they want the line suspended?",
                field_type="multiple_choice",
                choices=["yes", "no"],
            ),
        ],
    )

@agent.on_task_complete("lost_or_stolen")
def on_lost_or_stolen_done(call: guava.Call) -> None:
    st = state_for(call)
    assert st.customer is not None and st.phone_number is not None

    if call.get_field("suspend_confirmed") == "no":
        call.hangup(
            "Acknowledge the caller does not want to suspend the line right "
            "now, let them know they can call back anytime to do so, and end "
            "the call politely."
        )
        return

    device_status = call.get_field("device_status")
    suspend_line(st.phone_number)
    st.actions_taken.append(f"suspended line for device_status={device_status}")

    call.send_instruction("The line has been temporarily suspended. Confirm this with the caller in plain language.")
    call.hangup("Thank the caller, wish them well, and end the call.")

    
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