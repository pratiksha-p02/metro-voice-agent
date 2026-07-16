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
@agent.on_call_start
def on_call_start(call):
    call.set_task(
        "authenticate_customer",
        objective="""
        Verify the customer's identity before making account changes.

        Collect:
        1. Phone number associated with the account
        2. Account PIN

        Be polite and explain that verification is required
        for account security.
        """,
        checklist=[
            guava.Field(
                key="phone_number",
                description="Phone number associated with the Metro account"
            ),
            guava.Field(
                key="account_pin",
                description="Four digit account PIN"
            ),
        ],
    )

@agent.on_task_complete("authenticate_customer")
def on_authentication_complete(call):
    phone_number = call.get_field("phone_number")
    pin = call.get_field("account_pin")

    customer = lookup_customer(phone_number, pin)

    if customer is None:
        call.send_instruction(
            """
            Tell the customer the verification failed.
            Ask them to check their phone number and PIN
            and try again.
            """
        )
        return

    call.send_instruction(
        f"""
        The customer has been verified.

        Greet {customer['name']} and let them know
        you can help secure their account.
        """
    )

    call.set_task(
        "lost_or_stolen_device",
        objective="""
        Ask the customer whether their device was lost or stolen.

        Explain that the next step is protecting their account
        and confirming whether they want the line suspended.
        """,
        checklist=[
            guava.Field(
                key="device_status",
                description="Was the device lost or stolen?"
            ),
            guava.Field(
                key="suspend_confirmation",
                description="Does the customer want to suspend the line?"
            ),
        ],
    )

@agent.on_task_complete("lost_or_stolen_device")
def on_device_reported(call):
    status = call.get_field("device_status")
    confirmed = call.get_field("suspend_confirmation")
    if confirmed == "yes":
        call.send_instruction(
            "Tell the customer their line will now be suspended to protect the account."
        )
        # Temporary placeholder
        print(f"Suspending line. Device status: {status}")
    else:
        call.send_instruction(
            "Acknowledge the customer chose not to suspend the line."
        )

    print({
        "device_status": status,
        "suspend_confirmation": confirmed,
    })

    call.hangup(
        "Thank the customer for their time and end the call politely."
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