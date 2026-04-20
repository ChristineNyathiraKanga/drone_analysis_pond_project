# Drone Pond Management System

> **AI-powered pond water level analysis via drone imagery — built for Victory Farms.**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.41.1-red?logo=streamlit)](https://streamlit.io)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-green?logo=openai)](https://openai.com)
[![License](https://img.shields.io/badge/License-Internal-lightgrey)](#)

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Features](#2-features)
3. [System Architecture](#3-system-architecture)
4. [Prerequisites](#4-prerequisites)
5. [Installation](#5-installation)
6. [Configuration](#6-configuration)
7. [Usage](#7-usage)
8. [Module Reference](#8-module-reference)
9. [Image Capture Guidelines](#9-image-capture-guidelines)
10. [Water-Level Gauge Reference](#10-water-level-gauge-reference)
11. [Maintenance](#11-maintenance)
12. [Contributing Guidelines](#12-contributing-guidelines)

---

## 1. Introduction

The **Drone Pond Management System** is an AI-driven tool that uses drone imagery to automatically assess the water levels of fish ponds at Victory Farms. Drone operators upload pond images through a Streamlit web interface; the system analyzes each image using **OpenAI GPT-4o** and returns an instant, colour-coded recommendation indicating whether the pond needs urgent refilling, scheduled refilling, or no action.

Results are automatically:
- Displayed in the Streamlit UI with observation, recommendation, and AI explanation.
- Recorded to a **SharePoint Excel workbook** via the Microsoft Graph API.
- Distributed by **email** to relevant stakeholders.
- Optionally dispatched by **WhatsApp** or **SMS** notification.

The system supports both **single-image** and **SharePoint batch-processing** workflows, enabling efficient large-scale pond monitoring from a single session.

---

## 2. Features

| Feature | Description |
|---|---|
| Single Image Analysis | Upload one pond image and receive instant water-level assessment |
| SharePoint Batch Processing | Paste a SharePoint folder link to analyse dozens of images in one run |
| GPT-4o Vision | Uses OpenAI's multimodal model to count exposed gauge bands |
| SharePoint / Excel Logging | Appends results to a structured Excel table via Microsoft Graph API |
| Email Reporting | Sends an HTML summary table to farm managers after each batch run |
| WhatsApp Notifications | Optional push notifications via the Heyoo / Meta Business API |
| SMS Alerts | Optional SMS dispatch through a configurable SMS gateway |
| Async Batch Processing | Concurrent image processing with configurable batch size and semaphore |
| Robust JSON Parsing | Tolerates GPT output wrapped in markdown fences or single quotes |

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Drone Operator                        │
│   Uploads image or pastes SharePoint folder link       │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│               landing.py  (Streamlit UI)                │
│  ┌──────────────────┐   ┌──────────────────────────────┐│
│  │  Single Image    │   │  Batch (SharePoint Link)     ││
│  │  Processing      │   │  Processing                  ││
│  └────────┬─────────┘   └──────────────┬───────────────┘│
└───────────┼──────────────────────────────┼───────────────┘
            │                              │
            ▼                              ▼
┌─────────────────────────────────────────────────────────┐
│             reed_analyse.py  (Backend)                  │
│                                                         │
│  resize_image() → change_image_format() (base64)       │
│         ↓                                               │
│  compare_images() → OpenAI GPT-4o Vision               │
│         ↓                                               │
│  JSON response: band_count, observations,               │
│                 Recommendation, explanation             │
│         ↓                                               │
│  to_sheet_batch() → Microsoft Graph API → SharePoint   │
│  send_email_report() → Gmail SMTP                      │
│  send_whatsapp() / send_sms() → optional alerts        │
└─────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────┐
│          sharepoint_utils.py                            │
│  list_sharepoint_images() — lists images in a          │
│  SharePoint folder via Microsoft Graph API             │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Prerequisites

### 4.1 Python Environment

| Requirement | Version |
|---|---|
| Python | 3.10 or higher |
| pip | 23+ recommended |

### 4.2 Required Python Libraries

All dependencies are pinned in [`requirements.txt`](./requirements.txt).

| Library | Purpose |
|---|---|
| `streamlit==1.41.1` | Web UI framework |
| `openai==1.58.1` | GPT-4o Vision API client |
| `Pillow==10.4.0` | Image resizing before API call |
| `requests==2.28.1` | HTTP calls (SMS gateway, Graph API) |
| `numpy`, `pandas` | Data manipulation |
| `heyoo==0.1.2` | WhatsApp Business API (Meta) |
| `gspread==5.6.2` | Google Sheets (legacy; see note) |
| `msal==1.20.0` | Microsoft identity / Azure AD auth |
| `aiohttp==3.9.1` | Async HTTP for SharePoint image fetching |
| `pytz==2024.2` | Kenya timezone (Africa/Nairobi) |
| `oauth2client==4.1.3` | Google OAuth (legacy; see note) |
| `asyncio==3.4.3` | Async concurrency |
| `openpyxl==3.1.5` | Excel workbook support |
| `twilio==9.6.4` | Twilio SDK (optional SMS fallback) |

> **Note:** `gspread` and `oauth2client` are carried as legacy dependencies from an earlier Google Sheets integration. The active recording backend now uses Microsoft Graph API (SharePoint/Excel).

### 4.3 External Services & API Keys

| Service | Purpose | Where to Obtain |
|---|---|---|
| **OpenAI** | GPT-4o image analysis | [platform.openai.com](https://platform.openai.com) |
| **Azure App Registration** | Microsoft Graph API access for SharePoint | Azure Portal → App Registrations |
| **WhatsApp Business (Meta)** | Optional push notifications | [business.facebook.com](https://business.facebook.com) |
| **Gmail App Password** | SMTP email reports | Google Account → Security → App Passwords |
| **SMS Gateway** | Optional SMS alerts | Your SMS provider dashboard |
| **Heroku** (or equivalent) | Web hosting / deployment | [heroku.com](https://heroku.com) |

---

## 5. Installation

### 5.1 Clone the Repository

```bash
git clone https://github.com/<your-org>/drone-pond-management.git
cd drone-pond-management
```

### 5.2 Create and Activate a Virtual Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate — Windows
.venv\Scripts\activate

# Activate — macOS / Linux
source .venv/bin/activate
```

### 5.3 Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 6. Configuration

All secrets are loaded from **environment variables**. Never commit credentials to version control.

### 6.1 Create a `.env` File

Create a `.env` file at the project root (it is already listed in `.gitignore`):

```dotenv
# ── OpenAI ──────────────────────────────────────────────
OPENAI_API_KEY=sk-...

# ── Microsoft Graph API (SharePoint / Azure AD) ─────────
SP_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
SP_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
SP_CLIENT_SECRET=your-client-secret

# ── Gmail SMTP (for email reports) ──────────────────────
GMAIL_APP_PASSWORD=your-gmail-app-password

# ── WhatsApp Business API (optional) ────────────────────
WHATSAPP_TOKEN=your-whatsapp-access-token
WHATSAPP_PHONE_NUMBER_ID=your-phone-number-id

# ── SMS Gateway (optional) ──────────────────────────────
SMS_SENDER_ID=YourSenderID
SMS_API_KEY=your-sms-api-key
SMS_CLIENT_ID=your-sms-client-id
SMS_GATEWAY_URL=https://your-sms-gateway.com/api/send
```

### 6.2 Azure App Registration (Microsoft Graph)

The app uses a **Service Principal** (client-credentials flow) to write to the SharePoint Excel workbook.

1. In the Azure Portal, go to **App Registrations → New registration**.
2. Under **API Permissions**, add:
   - `Microsoft Graph → Application → Files.ReadWrite.All`
   - `Microsoft Graph → Application → Sites.ReadWrite.All`
3. Generate a **Client Secret** and copy the values into your `.env`.

---

## 7. Usage

### 7.1 Run Locally

```bash
# Ensure your virtual environment is active
streamlit run landing.py
```

The app will open in your browser at `http://localhost:8501`.

### 7.2 Single Image Analysis

1. In the **sidebar**, expand **Single Image Processing**.
2. Upload a pond image (`.png`, `.jpg`, or `.jpeg`).
3. Enter the **Pond Identifier** (e.g., `H1-P042`).
4. Select the **Pond Category** from the dropdown.
5. Click **Analyse Tube Structure for Image**.
6. View the results — **Observation**, **Recommendation**, and **Explanation** — rendered below the image.

### 7.3 Batch Analysis via SharePoint

1. In the **sidebar**, expand **Batch Processing (SharePoint Link)**.
2. Paste the SharePoint folder link containing drone images.
3. Click **Analyse Tube Structures from SharePoint**.
4. The app fetches all image files, analyses them concurrently, and displays each result.
5. After all images are processed, results are automatically written to the SharePoint Excel workbook.

### 7.4 Deploying to Heroku

```bash
# Login to Heroku
heroku login

# Create app (first time only)
heroku create your-app-name

# Set environment variables
heroku config:set OPENAI_API_KEY=sk-...
heroku config:set SP_TENANT_ID=...
# (repeat for all .env keys)

# Deploy
git push heroku main
```

The `Procfile` and `setup.sh` in the repository are pre-configured for Heroku deployment.

---

## 8. Module Reference

### 8.1 `landing.py` — Streamlit User Interface

| Component | Description |
|---|---|
| `st.set_page_config(layout="wide")` | Sets the page to full-width layout |
| `initialize_session_state()` | Primes `pond_prompt`, `uploaded_image`, `recommendation_data` in Streamlit session state |
| `get_prompt(submit_button)` | Returns `prompt_v4` (the active gauge analysis prompt) and caches it in session state |
| `safe_json_loads(s)` | Robust JSON parser — strips markdown fences, backticks, and language tags from GPT output before parsing |
| `extract_category_and_identifier(file_path)` | Parses folder/file path to derive pond category and identifier |
| `process_image(image_file, prompt)` | Wrapper that calls `compare_images()` and injects the pond identifier into the result dict |
| `process_images_in_batches(...)` | Async function that chunks image list and dispatches batches concurrently |
| `display_similarities(heading, information)` | Helper that renders a labelled section with a rainbow divider |
| **Single-image flow** | Upload → prompt selection → `compare_images()` → display + optional email |
| **Batch flow** | SharePoint link → `list_sharepoint_images()` → async processing → display → `to_sheet_batch()` |

### 8.2 `reed_analyse.py` — Backend Processing Engine

| Function | Description |
|---|---|
| `initialize_session_state()` | Mirrors the session-state setup from `landing.py` for safe import |
| `change_image_format(image_file)` | Reads binary image content and returns a `data:image/png;base64,...` data URL |
| `resize_image(image_file, max_size=1024)` | Resizes the image (preserving aspect ratio) to keep API payloads small |
| `compare_images(prompt, image_1)` | Core function — resizes image, encodes to base64, and calls `gpt-4o` via the OpenAI Chat Completions API |
| `async_compare_images(prompt, image_files, max_concurrent=15)` | Async version using `asyncio.Semaphore` and `loop.run_in_executor` for concurrency |
| `process_images_in_batches(prompt, image_files, batch_size=10)` | Splits image list into batches and calls `async_compare_images` per batch |
| `send_whatsapp(message, number)` | Sends a WhatsApp message using the `heyoo` library |
| `send_sms(receiver_list, msg)` | POSTs to a configurable SMS gateway URL; validates `+` prefixed numbers |
| `send_sms_recommendations(recommendation_data)` | Formats a batch of recommendations and dispatches them in chunked SMS messages (≤ 1605 chars) |
| `send_email_report(recommendation_data, ...)` | Builds an HTML table and sends it via Gmail SMTP (SSL, port 465) |
| `get_azure_token()` | Obtains an OAuth 2.0 bearer token from Azure AD using client credentials |
| `to_sheet(pond_identity, observation, recommendation, pond_category)` | Appends a single row to the SharePoint Excel table |
| `to_sheet_batch(recommendation_data)` | Appends multiple rows to the SharePoint Excel table in one session |
| `get_drive_and_item_from_sharing_url(sharing_url, token)` | Resolves a SharePoint sharing URL to a `(drive_id, item_id)` pair via the Microsoft Graph shares endpoint |

#### Active AI Prompt: `prompt_v4`

The current production prompt instructs GPT-4o to:

1. **Pre-check** — exclude the pipe rim/opening, water reflections, and dirt lines.
2. **Find the waterline** — locate the orange/red floating ring; estimate if absent.
3. **Count exposed white bands** — only bands above the waterline on the physical pipe.
4. **Confidence check** — returns `null` band count when visibility is poor.
5. **Return strict JSON** with keys: `band_count`, `confidence`, `ring_detected`, `observations`, `Recommendation`, `explanation`.

| Bands Exposed | Observation | Recommendation |
|:---:|---|---|
| 0 | White | No more filling — pond is full |
| 1 | Green | No action needed |
| 2 | Blue | Need to fill — water is low |
| 3 | Red | **Urgent pond refill** — critically low |

### 8.3 `sharepoint_utils.py` — SharePoint Image Listing

| Function | Description |
|---|---|
| `list_sharepoint_images(sharepoint_link)` | Authenticates via MSAL, resolves the sharing URL, and returns `(image_items, image_urls)` for all image files in the target folder |

---

## 9. Image Capture Guidelines

For optimal AI analysis accuracy, drone operators should follow these capture standards:

- **Angle:** Shoot at **45 degrees** from the drone, or as low as the safe flight envelope allows.
- **Framing:** Centre the **water level gauge** (black pipe with white bands) in the frame.
- **Clarity:** The **floating ring** and **white band(s)** must be clearly visible and in focus.
- **Exclusions:** Avoid unnecessary objects in the frame — nets, shadows, and reflections reduce accuracy.
- **Lighting:** Capture in good natural light; avoid harsh midday shadows directly on the gauge.
- **Naming:** Name each image file using the pond identifier (e.g., `H1-P042.jpg`) so it maps correctly in the Excel log.

---

## 10. Water-Level Gauge Reference

The active gauge design uses a **black vertical pipe** with **painted white bands** and a **floating orange/red ring** at the waterline.

```
  ┌───┐
  │   │  ← pipe top / rim  (DO NOT count)
  ╞═══╡  ← Band 3  ┐
  │   │             │  above water = pond is LOW
  ╞═══╡  ← Band 2  │
  │   │             │
  ●───●  ← floating ring (waterline)
  ╞═══╡  ← Band 1  ┘  (submerged — NOT counted)
  │   │
  │   │
```

| Bands Above Ring | Water Status | Action |
|:---:|---|---|
| 0 | Full | No more filling |
| 1 | Good | No action needed |
| 2 | Low | Fill pond |
| 3 | Critical | **Urgent refill** |

---

## 11. Maintenance

### 11.1 Software / Library Updates

| Component | Recommended Action |
|---|---|
| **Streamlit** | `pip install --upgrade streamlit` — run periodically |
| **OpenAI SDK** | Monitor for API-breaking changes; test after upgrades |
| **Heyoo / Meta WhatsApp** | Watch for Meta API version deprecations; update `WHATSAPP_TOKEN` before expiry |
| **MSAL** | Keep current to track Azure AD token endpoint changes |
| **All dependencies** | Run `pip list --outdated` quarterly; update and re-test |

### 11.2 External Service Monitoring

#### OpenAI
- **Plan:** Pay-as-you-go (credits-based).
- **Monitor:** Check the [OpenAI usage dashboard](https://platform.openai.com/usage) regularly.
- **Cost tip:** Review whether a lighter model (e.g., `gpt-4o-mini`) is sufficient if costs rise.

#### Heroku
- **Plan:** Free tier (subject to change; verify current Heroku free-tier policy).
- **Monitor:** Check dyno metrics; upgrade if memory or timeout errors increase.
- **Backups:** Store all environment variables in a secure secrets manager (e.g., Heroku Config Vars, Azure Key Vault).

#### Meta / WhatsApp Business API
- **Costs:** Based on conversation volume; monitor in the [Meta Business Manager](https://business.facebook.com).
- **Token hygiene:** Rotate `WHATSAPP_TOKEN` before it expires; store securely.
- **Throttling:** Minimise message frequency to stay within Meta's messaging limits.

#### Microsoft Graph / SharePoint
- **Service principal secret:** Azure client secrets expire (typically annually). Rotate `SP_CLIENT_SECRET` before expiry and update Heroku config vars.
- **Permissions:** Re-verify API permissions after any Azure tenant policy changes.

#### Gmail SMTP
- **App Password:** Re-generate if the Google account password changes.
- **Rate limits:** Gmail has daily send limits (~500 emails/day for standard accounts); monitor if notification volume grows.

---

## 12. Contributing Guidelines

We welcome contributions that improve accuracy, performance, or usability.

### 12.1 Branching Strategy

```
main          ← stable production branch
└── develop   ← integration branch
    └── feature/<short-description>
    └── fix/<short-description>
    └── chore/<short-description>
```

### 12.2 Getting Started

1. **Fork** the repository and clone your fork locally.
2. Create a new branch from `develop`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Copy `.env.example` (if provided) to `.env` and fill in your development credentials.
4. Install dependencies in a virtual environment (see [Installation](#5-installation)).

### 12.3 Code Standards

- Follow [PEP 8](https://peps.python.org/pep-0008/) for Python style.
- Add a docstring to every new function.
- Do **not** commit `.env`, API keys, service account JSON files, or any credentials.
- Keep functions small and single-purpose.
- Update `requirements.txt` if you add new dependencies (`pip freeze > requirements.txt` is acceptable for prototyping, but prefer pinning exact versions).

### 12.4 Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
feat: add async retry logic for GPT-4o API calls
fix: correct band-count off-by-one when ring is partially visible
docs: update README with SharePoint batch instructions
chore: bump openai SDK to 1.60.0
```

### 12.5 Pull Requests

1. Push your branch and open a **Pull Request** against `develop`.
2. Fill in the PR template describing:
   - **What** changed and **why**.
   - **How** you tested it (manual steps or automated tests).
   - Any **breaking changes** or deployment steps required.
3. Request a review from a maintainer.
4. PRs require at least **1 approval** before merging.
5. Squash commits on merge to keep `develop` history clean.

### 12.6 Reporting Bugs

Open a GitHub Issue with:
- A clear title.
- Steps to reproduce.
- Expected vs. actual behaviour.
- Relevant logs or screenshots (redact any credentials).

---

## Acknowledgements

Built by the **Technology & Innovation team** at [Victory Farms](https://victoryfarmskenya.com).  
Powered by [OpenAI GPT-4o](https://openai.com), [Streamlit](https://streamlit.io), and [Microsoft Graph API](https://learn.microsoft.com/en-us/graph/overview).
