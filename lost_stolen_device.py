from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from typing import Any
import logging
import random
from datetime import datetime, timezone
from dotenv import load_dotenv


import guava
from guava import Agent
from guava import SuggestedAction
from guava import Client
from guava.helpers.rag import DocumentQA
client = Client()
load_dotenv()

import gspread

gc = gspread.service_account(
    filename=os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
)

logger = logging.getLogger("metro.lost_stolen_device")

# The Sheets workbook acts as a lightweight backend for this sandboxed demo instead of a real carrier API.
spreadsheet = gc.open("guavaCustomerSupport")

customers_sheet = spreadsheet.worksheet("Customers")
logs_sheet = spreadsheet.worksheet("InteractionLog")

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

Reporting a Stolen Device
Customers who believe their device was stolen, rather than misplaced, should
file a report with their local law enforcement agency. They should keep note
of their device's I-M-E-I number, which the assistant can help confirm, in case
it's requested during the investigation.

SIM and eSIM
A suspended line can be reactivated on a replacement device once the customer
either inserts their existing SIM card or has an eSIM re-provisioned in
store or through account self-service.
"""

_OTP_STORE: dict[str, str] = {}

def lookup_customer(phone_number: str, pin: str):
    phone_number = _normalize_phone(phone_number).replace("+", "")

    records = customers_sheet.get_all_records()

    for row in records:
        if str(row["Phone"]) == phone_number and str(row["PIN"]).strip() == pin.strip().lstrip("0") :
            return {
                "name": row["Name"],
                "pin": str(row["PIN"]),
                "account_status": row["Status"],
                "account_type": row["Account Type"],
                "otp_target_phone": str(row["OTP Phone"]).strip() or None,
                "device": {
                    "model": row["Device"],
                    "imei": row["IMEI"],
                },
            }

    return None


def suspend_line(phone_number: str) -> bool:
    """
    Suspend the line only after verification; this is the security-sensitive backend action that protects the account.
    Returns True only if the customer's status was successfully updated.
    """

    try:
        phone_number = _normalize_phone(phone_number).replace("+", "")

        records = customers_sheet.get_all_records()

        headers = customers_sheet.row_values(1)

        phone_col = headers.index("Phone") + 1
        status_col = headers.index("Status") + 1

        for row_index, row in enumerate(records, start=2):

            if str(row["Phone"]).strip() == phone_number:

                current_status = str(row["Status"]).strip().lower()

                # Already suspended
                if current_status == "suspended":
                    logger.info(
                        "Line %s is already suspended",
                        phone_number
                    )
                    return True

                # Update status column
                customers_sheet.update_cell(
                    row_index,
                    status_col,
                    "suspended"
                )

                logger.info(
                    "Successfully suspended line %s",
                    phone_number
                )

                return True

        logger.warning(
            "Could not find customer with phone %s",
            phone_number
        )

        return False

    except Exception as e:
        logger.error(
            "Failed to suspend line %s: %s",
            phone_number,
            e
        )

        return False

def log_interaction(record: dict[str, Any]) -> None:
    """Write a post-call summary row to the InteractionLog sheet."""
    logs_sheet.append_row([
        record["timestamp"],
        record["customer_name"],
        record["phone"],
        record["actions_performed"],
        record["escalated"],
        record["escalation_reason"],
        record["sentiment"],
    ])

def send_otp(target_phone: str) -> None:
    """Mock SMS delivery for the sandboxed demo; real OTP transport is intentionally omitted here."""
    code = f"{random.randint(0, 999999):06d}"
    _OTP_STORE[target_phone] = code
    logger.info("[MOCK SMS] OTP %s sent to %s", code, target_phone)

# def send_otp(target_phone: str) -> None:
#     code = f"{random.randint(0, 999999):06d}"

#     target_phone = _normalize_phone(target_phone)

#     _OTP_STORE[target_phone] = code

#     client.send_sms(
#         from_number="+14849986369",
#         to_number=target_phone,
#         message=f"Your verification code is {code}"
    
#     )   

def verify_otp(target_phone: str, submitted_code: str) -> bool:
    expected = _OTP_STORE.get(target_phone)
    return expected is not None and submitted_code.strip() == expected



def check_replacement_eligibility(customer: dict[str, Any]) -> dict[str, Any]:
    """Return simplified replacement guidance based on the customer's plan."""
    return {
        "eligible_for_discounted_replacement": customer["account_type"] == "multi_line",
        "eligible_for_upgrade": True,
    }

def _normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits


MAX_AUTH_RETRIES = 2
MAX_OTP_RETRIES = 2

# Keep call state in a deterministic dictionary outside the LLM so the conversation can advance safely across tasks.
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
        "verify their identity, suspend the affected line and guide them "
        "through replacement options."
    ),
)
@agent.on_call_received
def on_call_received(call_info: guava.CallInfo) -> guava.IncomingCallAction:
    return guava.AcceptCall()


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
            "on the account and their account PIN. Be calm, understanding, and reassuring as "
            "this is often a stressful moment for the caller."
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
            st.escalated = True
            st.escalation_reason = "authentication failed"
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

   
    if st.otp_attempts >= MAX_OTP_RETRIES:
        st.escalated = True
        st.escalation_reason = "OTP verification failed"
        call.hangup(
            "Apologize that the verification code could not be confirmed after "
            "multiple attempts. For security reasons, explain that you can't "
            "make account changes right now, and direct the caller to visit a "
            "Metro by T-Mobile store with a valid government-issued photo ID "
            "or offer to connect them with a customer support "
            "representative. Do not disclose or guess at any account details."
        )
        return

    call.send_instruction(
        "That code didn't match. Apologize and ask the caller to read the "
        "verification code back one more time."
    )
    call.set_task(
        "otp_verification",
        objective="Re-collect the one-time verification code.",
        checklist=[guava.Field(key="otp_code", description="The one-time verification code sent via SMS")],
    )


# Transition from verification to the device-resolution stage of the conversation.
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
        call.send_instruction(
        "The caller does not want to suspend the line right now. "
        "Acknowledge their choice, let them know they can request suspension "
        "later, and ask if there is anything else you can help with."
        )

        call.set_task(
        "general_support",
        objective=(
            "Help the caller with any additional questions they have. "
            "Do not attempt to suspend the line unless they explicitly request it."
            ),
        checklist=[
            "Ask if there is anything else you can help with.",
            "Answer any questions using available support information.",
            "End the call politely when the caller is finished."
            ],
        )
        return

    device_status = call.get_field("device_status")
    suspended_ok = suspend_line(st.phone_number)

    if not suspended_ok:
        st.escalated = True
        st.escalation_reason = "line suspension API failure"
        call.transfer(
            destination=os.environ.get("SUPPORT_TRANSFER_NUMBER", "+18005550100"),
            instructions=(
                "Apologize that there was a technical issue suspending the "
                "line, reassure the caller their request is being handled, "
                "and let them know you're connecting them with a support "
                "representative who can complete this manually."
            ),
        )
        return

    st.actions_taken.append(f"suspended line for device_status={device_status}")
    call.send_instruction("The line has been temporarily suspended. Confirm this with the caller in plain language.")

    if device_status == "stolen":
        imei = st.customer["device"]["imei"]
        call.add_info(
            "stolen_device_guidance",
            {
                "advice": (
                    "Because the device was stolen rather than lost, advise the "
                    "caller to file a report with their local law enforcement "
                    "agency, and let them know their device I-M-E-I may be "
                    f"requested during that process: {imei}."
                )
            },
        )

    _offer_replacement_guidance(call)

@agent.on_task_complete("general_support")
def on_general_support_done(call: guava.Call) -> None:
    call.hangup(
        "Thank the caller and end the call politely."
    )

# Transition to replacement guidance once the account is secured.
def _offer_replacement_guidance(call: guava.Call) -> None:
    st = state_for(call)
    assert st.phone_number is not None

    eligibility = check_replacement_eligibility(st.customer)
    call.add_info("replacement_eligibility", eligibility)

    call.set_task(
        "replacement_guidance",
        objective=(
            "Now that the account is secure, walk the caller through their "
            "device replacement options based on the eligibility information "
            "you have, and answer any follow-up questions. When they're ready "
            "to end the call, close warmly."
        ),
        checklist=[
            "Explain the caller's replacement options based on their "
            "eligibility, and mention they can also visit a Metro by "
            "T-Mobile store or speak with a support specialist.",
            "Ask if there's anything else you can help with before ending the call.",
        ],
    )


@agent.on_task_complete("replacement_guidance")
def on_replacement_guidance_done(call: guava.Call) -> None:
    call.hangup("Thank the caller, wish them well, and end the call.")


# ---------------------------------------------------------------------------
# 4. Escalation & Safety Behavior
# ---------------------------------------------------------------------------

REP_REQUEST_KEY = "representative"


@agent.on_action_request
def on_action_request(call: guava.Call, request: str) -> SuggestedAction | None:
    lowered = request.lower()
    if any(kw in lowered for kw in ("representative", "agent", "human", "speak to someone", "manager")):
        return SuggestedAction(key=REP_REQUEST_KEY)
    return None


# Human handoff is treated as a safe escalation path when the caller asks for an agent.
@agent.on_action(REP_REQUEST_KEY)
def on_representative_requested(call: guava.Call) -> None:
    st = state_for(call)
    st.escalated = True
    st.escalation_reason = "caller requested a representative"
    call.transfer(
        destination=os.environ.get("SUPPORT_TRANSFER_NUMBER", "+18005550100"),
        instructions=(
            "Acknowledge the caller's request, briefly summarize what's "
            "happened on the call so far, and let them know you're "
            "connecting them with a representative now."
        ),
    )


@agent.on_session_end
def on_session_end(call: guava.Call, event: guava.events.BotSessionEnded) -> None:
    st = state_for(call)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "customer_name": st.customer["name"] if st.customer else None,
        "phone": st.phone_number,
        "actions_performed": ", ".join(st.actions_taken),
        "escalated": st.escalated,
        "escalation_reason": st.escalation_reason,
        "sentiment": "neutral",
    }
    try:
        log_interaction(record)
    except Exception as e:
        logger.error("Failed to sync log to sheets: %s", e)



# Entry point: start the agent in the selected runtime mode.
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