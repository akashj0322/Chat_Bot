# Chat_Bot
# AppGuide: Internal App Directory Bot

An AI-powered bot that tells employees **which internal application to use** for a task, running entirely on a local laptop.

Employees describe what they want in their own words ("book a flight for a client visit"), and the bot replies with the right app (Travel Desk), who approves, and a button to open it.

**Stack:** Python 3.13 · FastAPI · SQL Server 2025 · Foundry Local (phi-4-mini) · Bot Framework Emulator · Adaptive Cards

---

## The Problem

Companies run dozens of internal apps (leave, timesheets, travel, expenses, payslips, IT tickets...). Staff keep asking *"Where do I go to do X?"*, which costs colleagues, HR and helpdesk time. Employees think in **tasks**; company information is organised by **application name**. This bot bridges that gap instantly.

## Key Features

- **Fast**: common questions are answered in under a second from stored FAQs.
- **Grounded**: every URL, contact and access rule comes from the database. The AI never invents a link.
- **Always answers**: if the LLM is slow or offline, the bot falls back to keyword matching.
- **Honest**: unknown questions get "I couldn't find an app", not a made-up answer.
- **Self-improving**: every question is logged to `QueryLog`, so the team can see what people ask and add new FAQs.
- **Multi-channel**: the same logic runs in a terminal, a web API and a chat bot (Teams-ready).

## How It Works: the 4-Step Pipeline

| Step | What happens |
|------|--------------|
| 1. **FAQ match** | Important words are compared with stored FAQ questions. If at least 60% overlap in both directions, the stored answer is returned (no LLM). |
| 2. **Keyword shortlist** | Every *Active* app is scored: name x3, keywords x2, description x1, category x0.5. The top 5 are kept. |
| 3. **LLM picks** | The model chooses 1 of the 5 candidates and writes a friendly sentence, replying in JSON: `{"app_id": ..., "answer": ...}`. |
| 4. **Log + reply** | The question and result are saved to `QueryLog`; the reply is sent as text or an Adaptive Card with "Open app" buttons. |

**Safety net:** if the model times out, returns bad JSON, or names an app that was not in the list, the bot uses the top keyword match instead.

## Architecture

```
Bot Emulator / Teams ─┐
Browser (/docs) ──────┼──> main.py (FastAPI :8024) ──> bot_logic.py ──> SQL Server (DevDB)
Terminal chat ────────┘        (local_chat.py calls         │            ├─ Applications
                                bot_logic.py directly)       │            ├─ FAQs
                                                             │            └─ QueryLog
                                                             └──> LLM: Foundry Local (phi-4-mini)
                                                                       | Azure OpenAI | none
```

| Layer | Local (this project) | Production (cloud) |
|-------|---------------------|--------------------|
| Chat channel | Bot Framework Emulator | Microsoft Teams via Azure Bot Service |
| Web server | `python main.py` | Azure App Service / Container Apps |
| Database | SQL Server 2025 Developer | Azure SQL Database |
| Language model | Foundry Local, phi-4-mini | Azure OpenAI (e.g. GPT-4o-mini) |

## Project Structure

| File | Purpose |
|------|---------|
| `bot_logic.py` | The brain: config, DB queries, FAQ + keyword matching, LLM call, logging, Adaptive Card |
| `main.py` | FastAPI server: `/health`, `/ask` (JSON), `/api/messages` (bot channel) |
| `local_chat.py` | Terminal chat for quick testing (no server needed) |
| `setup_local_db.sql` | Creates `DevDB`, the 3 tables and sample data |
| `.env.example` | Template of settings (copy to `.env`) |
| `requirements.txt` | Python dependencies |

## Database Design (DevDB)

- **Applications**: `app_id, app_name, category, short_description, url, keywords, access_notes, owner_contact, status` (only `Active` rows are suggested)
- **FAQs**: `faq_id, question, answer, related_app_id`
- **QueryLog**: `log_id, user_query, matched_type (FAQ / APP / NONE), matched_id, teams_user, created_at`

## Prerequisites

- Windows 10/11 (64-bit), 8 GB RAM minimum (16 GB recommended), 15 GB free disk
- Python 3.13
- Visual Studio Code + Python extension
- SQL Server 2025 Developer edition, SSMS 22 and `sqlcmd`
- ODBC Driver 18 for SQL Server
- Foundry Local + `phi-4-mini` model (optional, ~2.2 GB download)
- Bot Framework Emulator

> **Low on RAM?** Cap SQL Server memory to 1 GB, or set `LLM_PROVIDER=none` to run with FAQ + keyword matching only.

## Getting Started

### 1. Clone and create a virtual environment

```powershell
git clone https://github.com/YOUR-USERNAME/app_bot_project.git
cd app_bot_project
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Create the database

```powershell
sqlcmd -S localhost -E -C -i setup_local_db.sql
```

Expected: a summary showing `Applications 9, FAQs 4, QueryLog 0` (8 active apps plus 1 retired app used to prove retired apps are ignored).

### 3. Configure `.env`

Copy `.env.example` to `.env` and fill in your values (one setting per line, no quotes, no spaces around `=`):

| Setting | Example / Notes |
|---------|-----------------|
| `LLM_PROVIDER` | `local` (Foundry Local), `azure` (Azure OpenAI) or `none` (keywords only) |
| `LOCAL_LLM_BASE_URL` | `http://127.0.0.1:<port>/v1` (port from `foundry status`; it can change on restart) |
| `LOCAL_LLM_MODEL` | Must match the id from `/v1/models`, e.g. `phi-4-mini-instruct-openvino-gpu` |
| `LLM_TIMEOUT_SECONDS` | `90` |
| `SQL_CONNECTION_STRING` | `Driver={ODBC Driver 18 for SQL Server};Server=localhost;Database=DevDB;Trusted_Connection=yes;TrustServerCertificate=yes;` |
| `SQL_SCHEMA` | `dbo` |
| `HOST` / `PORT` | `127.0.0.1` / `8024` |
| `MicrosoftAppId` / `MicrosoftAppPassword` | Leave empty for local use |

> **Never commit your real `.env`.** It is listed in `.gitignore`.

### 4. Run it (three ways)

| Way | Command | Use it to |
|-----|---------|-----------|
| **A. Terminal chat** | `python local_chat.py` | Test DB + LLM with nothing else running |
| **B. Web API** | `python main.py`, then open http://127.0.0.1:8024/docs | Call `/ask` and see raw JSON |
| **C. Chat bot** | `python main.py`, then in Emulator: Open Bot -> `http://localhost:8024/api/messages` | See the full chat experience with Adaptive Cards |

If using the local LLM, start it first: `foundry model load phi-4-mini`, then check the port with `foundry status` and update `.env`.

## Example

```
You: How do I apply for leave?
Bot [FAQ FAQ001]: Open the HRMS Leave Portal, choose Apply Leave, pick the leave type and dates, and submit.
 -> HRMS Leave Portal: https://intranet.example.com/hrms/leave

You: I need to book a flight for a client visit
Bot [APP APP003]: The Travel Desk app is the right choice for booking flights for your client visit...
 -> Travel Desk: https://intranet.example.com/travel
```

`[FAQ ...]` means the answer came instantly from step 1. `[APP ...]` means steps 2-3 (shortlist + LLM) produced it.

### API

```http
POST /ask
{"query": "I need to book a flight"}
```

Returns `text`, `matched_type`, `matched_id`, `app` and `suggestions`. `GET /health` returns `{"status": "ok"}`.

## Test Cases

| Question | Expected | Proves |
|----------|----------|--------|
| How do I apply for leave? | FAQ FAQ001 | DB connection + FAQ matching |
| Where can I download my payslip? | FAQ FAQ004 | FAQ links to an app |
| I need to book a flight for a client visit | APP APP003 | LLM understands meaning |
| my vpn is not working | APP APP005 | Keywords + LLM |
| fill timesheet | APP APP002 | Near-miss FAQ falls through correctly |
| quantum banana | NONE | Bot admits it does not know |
| (any leave question) | never APP099 | Retired apps are never suggested |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Activate.ps1 ... running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `Missing settings ... .env` | Run from the project folder; `.env` must sit next to `bot_logic.py` |
| `Cannot open database "DevDB"` | Run `setup_local_db.sql`; use `Server=localhost` |
| SSL / certificate error | Keep `TrustServerCertificate=yes` (local only) |
| `LLM call failed ... using keyword match` | Port changed, model not loaded or wrong model id; check `foundry status` |
| Emulator `401 Unauthorized` | Leave App ID and Password empty |
| Port 8024 already in use | Close the old `main.py` or change `PORT` in `.env` |

## Roadmap

1. Data modelling: add your own apps and FAQs
2. Retrieval without AI: tune tokenising and scoring weights
3. Adding the LLM: prompt, JSON output, validation
4. Web API: add a `GET /apps` endpoint
5. Chat channel: add a "Was this helpful?" button
6. Observability: turn top unanswered (`NONE`) questions into FAQs
7. To the cloud: Azure SQL, Azure OpenAI, Azure Bot Service + Teams (`LLM_PROVIDER=azure`, no code change)

## Key Concept: Grounding

The AI decides *which* app and phrases the answer, but every fact the user can act on (app name, URL, contact, access rule) comes from the database. This keeps the assistant trustworthy.

## License

Add your license here (e.g. MIT).
