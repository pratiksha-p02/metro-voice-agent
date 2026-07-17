from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from typing import Any
import logging
import random

import guava
from guava import Agent
from guava.helpers.rag import DocumentQA
logger = logging.getLogger("metro.lost_stolen_device")



SUPPORT_KB = """
Device Replacement Options
Customers with an active protection plan can order a replacement device online,
by phone, or in a Metro by T-Mobile store. Customers without a protection plan
can purchase a new device at full retail price, or a discounted upgrade price
if they are eligible for an upgrade.

Store Support
Customers can find their nearest Metro by T-Mobile store using the store
locator at metrobyt-mobile.com/stores. Bring a valid government-issued photo
ID for any in-store account changes.

Account Recovery
If a customer cannot be verified over the phone (for example, they don't
remember their PIN), they must visit a store in person with a valid
government-issued photo ID to regain access to their account.

SIM and eSIM
A suspended line can be reactivated on a replacement device once the customer
either inserts their existing SIM card or has an eSIM re-provisioned in
store or through account self-service.
"""

CUSTOMERS = {
    "+15551234567": {
        "name": "Jordan Alvarez",
        "pin": "4821",
        "account_type": "multi_line",
        "otp_target_phone": "+13233311758", 
    },
    "+15552223333": {
        "name": "Priya Natarajan",
        "pin": "0099",
        "account_type": "single_line",
        "otp_target_phone": None,           
    },
}

_OTP_STORE: dict[str, str] = {}

def lookup_customer(phone_number: str, pin: str) -> dict[str, Any] | None:
    """MOCK: verify phone + PIN against the customer data source."""
    record = CUSTOMERS.get(_normalize_phone(phone_number))
    if record and record["pin"] == pin:
        return record
    return None

def send_otp(target_phone: str) -> None:
    """MOCK: send a one-time code via SMS to the secondary verified number."""
    code = f"{random.randint(0, 999999):06d}"
    _OTP_STORE[target_phone] = code
    logger.info("[MOCK SMS] OTP %s sent to %s", code, target_phone)

def verify_otp(target_phone: str, submitted_code: str) -> bool:
    expected = _OTP_STORE.get(target_phone)
    return expected is not None and submitted_code.strip() == expected

def suspend_line(phone_number: str) -> bool:
    """MOCK: call the account-management API to suspend the line."""
    return True

def suspend_line(phone_number: str) -> bool:
    """MOCK: call the account-management API to suspend the line."""
    return True

def check_replacement_eligibility(phone_number: str) -> dict[str, Any]:
    """MOCK: look up device replacement eligibility from an external service."""
    record = CUSTOMERS.get(_normalize_phone(phone_number))
    has_protection_plan = record is not None and record["account_type"] == "multi_line"
    return {
        "eligible_for_discounted_replacement": has_protection_plan,
        "eligible_for_upgrade": True,
        "nearest_store_hint": "use the store locator at metrobyt-mobile.com/stores",
    }

def _normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits

# ---------------------------------------------------------------------------
# Per-call state management
# ---------------------------------------------------------------------------
MAX_AUTH_RETRIES = 2
MAX_OTP_RETRIES = 2

@dataclass
class CallState:
    authenticated: bool = False
    customer: dict[str, Any] | None = None
    phone_number: str | None = None
    auth_attempts: int = 0
    otp_attempts: int = 0 
    escalated: bool = False            
    escalation_reason: str | None = None
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
document_qa = DocumentQA(documents=SUPPORT_KB) 
@agent.on_question
def on_question(call: guava.Call, question: str) -> str:
    """Retrieve answers dynamically from our local KB when asked an out-of-flow question."""
    return document_qa.ask(question)
@agent.on_call_start
def on_call_start(call: guava.Call) -> None:
    state_for(call)
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
        if st.auth_attempts >= MAX_AUTH_RETRIES:
            call.hangup(
                "Apologize that you're unable to verify the account after "
                "multiple attempts for security reasons. Direct the caller to "
                "visit a Metro by T-Mobile store with a valid government-issued "
                "photo ID, or offer to connect them with a customer support "
                "representative. Do not disclose or guess at any account details."
            )
            return

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

    if record["account_type"] == "multi_line" and record.get("otp_target_phone"):
        send_otp(record["otp_target_phone"])
        call.set_task(
            "otp_verification",
            objective=(
                "This account is on a multi-line plan, so a one-time "
                "verification code was just texted to another number on the "
                "account. Ask the caller to read that code back to you."
            ),
            checklist=[guava.Field(key="otp_code", description="The one-time verification code sent via SMS")],
        )
    else:
        _begin_device_resolution(call, record["name"])

@agent.on_task_complete("otp_verification")
def on_otp_done(call: guava.Call) -> None:
    st = state_for(call)
    record = st.customer
    assert record is not None

    submitted_code = str(call.get_field("otp_code"))
    st.otp_attempts += 1

    if verify_otp(record["otp_target_phone"], submitted_code):
        st.authenticated = True
        _begin_device_resolution(call, record["name"])
        return

    # Check if we hit the limit
    if st.otp_attempts >= MAX_OTP_RETRIES:
        st.escalated = True
        st.escalation_reason = "OTP verification failed"
        call.hangup(
            "Apologize that the verification code could not be confirmed after "
            "multiple attempts. For security reasons, explain that you can't "
            "make account changes right now, and direct the caller to visit a "
            "Metro by T-Mobile store with a valid government-issued photo ID "
            "or speak with a support representative."
        )
        return

    # Fallback retry warning
    call.send_instruction(
        "That code didn't match. Apologize and ask the caller to read the "
        "verification code back one more time."
    )
    call.set_task(
        "otp_verification",
        objective="Re-collect the one-time verification code.",
        checklist=[guava.Field(key="otp_code", description="The one-time verification code sent via SMS")],
    )


def _begin_device_resolution(call: guava.Call, customer_name: str) -> None:
    st = state_for(call)
    st.authenticated = True
    call.send_instruction(
        f"The caller is verified as {customer_name}. Greet them by name and "
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

    # Check database to see if this specific customer is eligible for promotions
    eligibility = check_replacement_eligibility(st.phone_number)
    has_discount = eligibility["eligible_for_discounted_replacement"]

    call.send_instruction(
        f"The line has been temporarily suspended. Inform the customer of this.\n\n"
        f"Next, share their device replacement eligibility:\n"
        f"- Eligible for low-cost insurance replacement: {'YES (device protection active)' if has_discount else 'NO'}\n"
        f"- Eligible for promotional upgrade: {'YES' if eligibility['eligible_for_upgrade'] else 'NO'}\n\n"
        f"Now, let's find out how they want to handle getting their replacement."
    )

    call.set_task(
        "device_replacement",
        objective=(
            "Discuss replacement device fulfillment options. Find out if they "
            "prefer to pick up a replacement in a local Metro retail store, "
            "or if they want one shipped directly to their home address."
        ),
        checklist=[
            guava.Field(
                key="replacement_preference",
                description="How does the customer want to receive their new device?",
                field_type="multiple_choice",
                choices=["store", "shipping"],
            ),
        ],
    )

@agent.on_task_complete("device_replacement")
def on_device_replacement_done(call: guava.Call) -> None:
    st = state_for(call)
    preference = call.get_field("replacement_preference")
    st.actions_taken.append(f"selected replacement preference: {preference}")

    if preference == "store":
        call.send_instruction(
            "Inform the customer they can head over to any Metro by T-Mobile store. "
            "Remind them that they MUST bring a valid government-issued photo ID "
            "in order to complete a physical swap or activate a new SIM card."
        )
    else:
        call.send_instruction(
            "Advise the customer that an order confirmation email and tracking link "
            "will be dispatched shortly. Remind them that standard shipping takes "
            "between 3 to 5 business days."
        )

    call.hangup("Warmly thank the customer for using Metro support, ask if there is "
                "anything else they need, and end the call beautifully.")

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