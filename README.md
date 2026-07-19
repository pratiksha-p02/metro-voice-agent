# Metro by T-Mobile Lost or Stolen Device Voice Agent

## Overview

This project implements a voice AI customer support agent using the Guava SDK. The agent assists Metro by T-Mobile customers who have lost or had their device stolen by securely authenticating them, suspending their line upon confirmation, and guiding them through their next steps.

To simulate a production environment, the agent integrates with **Google Sheets as a lightweight external backend**, where customer records are retrieved and post-call interactions are logged instead of using hardcoded data.

## Features

- Phone number and PIN authentication
- OTP verification for multi-line accounts
- Line suspension after customer confirmation
- Device replacement guidance
- FAQ support using Guava's `DocumentQA`
- Human representative escalation
- Post-call interaction logging to Google Sheets

---

## Project Structure

```text
.
├── lost_stolen_device.py
├── requirements.txt
├── README.md
└── service_account.json (not committed)
```

---

## What I Deliberately Chose Not to Build

Given the project's intended scope (approximately 8–10 hours), I intentionally focused on implementing the core customer support workflow instead of attempting to simulate every Metro backend capability.

The following production features were intentionally left out:

- **Real carrier backend integrations.** Customer information is stored in Google Sheets rather than Metro's internal systems.
- **Live SMS delivery.** OTP generation is implemented, but delivery remains mocked instead of integrating with an SMS provider.
- **Replacement ordering workflow.** The agent explains available replacement options but does not place replacement orders or schedule shipments.
- **Dynamic store lookup.** The agent directs customers to Metro's store locator instead of querying nearby stores.
- **Automatic sentiment analysis.** Interaction logs currently record a default sentiment rather than analyzing the conversation transcript.
- **Persistent session storage.** Call state and OTPs are stored in memory instead of Redis or another persistent datastore.

These decisions allowed me to spend more time building reliable authentication, backend integration, conversational flow, and error handling.

---

## Running the Project

### Prerequisites

- Python 3.11+
- Guava SDK
- Google Cloud service account credentials
- Google Sheet shared with the service account

### Setup

1. Clone the repository.

2. Install the Guava SDK by following the official setup instructions.

3. Install the remaining Python dependencies:

```bash
pip install -r requirements.txt
```

4. Create a `.env` file containing:

```text
GUAVA_API_KEY=...
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
GUAVA_AGENT_NUMBER=...

```

5. Share the Google Sheet with the Google service account email.

6. Run the agent:

```bash
python lost_stolen_device.py --chat
```

or

```bash
python lost_stolen_device.py --local
```

or

```bash
python lost_stolen_device.py --webrtc
```

or

```bash
python lost_stolen_device.py --phone
```

---

## With Another 8 Hours

Given another development iteration, I would prioritize:

- Replacing Google Sheets with real carrier backend APIs
- Integrating live SMS delivery for OTP verification
- Persisting call state in Redis for production reliability
- Adding transcript-based sentiment analysis
- Expanding the replacement flow to support device ordering and appointment scheduling
- Adding automated tests and improving monitoring around authentication failures and escalations

---

## AI Usage Note

I used ChatGPT, Claude and Gemini primarily for brainstorming, SDK understanding, implementation guidance and code review. During planning, I used it to evaluate different customer support scenarios, refine the conversational flow, and think through authentication and escalation strategies. During implementation, I used it to better understand the Guava SDK, generate initial code drafts, and review portions of the codebase for readability and maintainability.

I did not treat AI-generated code as final. For example, early drafts relied on hardcoded mock dictionaries, but I replaced those with a Google Sheets integration to better reflect a realistic external system. I also simplified several generated designs that introduced more abstraction than I felt was appropriate for an 8–10 hour project, keeping the architecture focused and maintainable.

Rather than generating the entire project end-to-end, I implemented and tested the application incrementally. I preferred understanding each SDK callback and backend interaction before incorporating it, modifying generated code where necessary to fit the conversational flow and implementation choices I wanted. My goal was to use AI to accelerate development while still making the architectural and implementation decisions myself.

---

## Development

The repository preserves the project's commit history to reflect how the implementation evolved incrementally—from an initial conversational flow, to per-call state management, OTP verification, Google Sheets integration, authentication hardening, FAQ support, and interaction logging.
