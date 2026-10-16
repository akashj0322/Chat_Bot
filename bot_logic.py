"""
App Navigator Bot - core logic.

Flow for every question:
  1. FAQ match       - if a stored FAQ is a close match, answer from it.
  2. Keyword filter  - score Active apps by name/keywords/description overlap.
  3. LLM pick        - the LLM (Azure OpenAI or local) chooses the best candidate and phrases the reply.
                       (If the LLM call fails, the top keyword match is returned.)
  4. Log             - every question is written to QueryLog.

Required .env variables (file sits next to this script):
    SQL_CONNECTION_STRING      full ODBC connection string
    LLM_PROVIDER               azure (default) | local | none
  When LLM_PROVIDER=azure:
    AZURE_OPENAI_ENDPOINT      e.g. https://<resource>.openai.azure.com/
    AZURE_OPENAI_API_KEY
    AZURE_OPENAI_DEPLOYMENT    e.g. gpt-35-turbo
  When LLM_PROVIDER=local (Foundry Local or any OpenAI-compatible server):
    LOCAL_LLM_BASE_URL         e.g. http://127.0.0.1:51269/v1
    LOCAL_LLM_MODEL            exact id from GET <base_url>/models
  When LLM_PROVIDER=none: keyword matching only, no LLM call.
Optional:
    AZURE_OPENAI_API_VERSION   default 2024-08-01-preview
    LOCAL_LLM_API_KEY          default "not-needed"
    LLM_TIMEOUT_SECONDS        default 60
    SQL_SCHEMA                 default dbo  (use "appnav" if tables live there)
"""
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from THIS file's folder, regardless of where python is launched.
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

import pyodbc  # noqa: E402
from openai import AzureOpenAI, OpenAI  # noqa: E402

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "azure").strip().lower()
if LLM_PROVIDER not in {"azure", "local", "none"}:
    sys.exit(f"Invalid LLM_PROVIDER: {LLM_PROVIDER!r} (use azure, local or none)")

REQUIRED_VARS = ["SQL_CONNECTION_STRING"]
if LLM_PROVIDER == "azure":
    REQUIRED_VARS += ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"]
elif LLM_PROVIDER == "local":
    REQUIRED_VARS += ["LOCAL_LLM_BASE_URL", "LOCAL_LLM_MODEL"]


def check_config() -> None:
    """Fail early with a readable message instead of a KeyError."""
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        where = ENV_PATH if ENV_PATH.exists() else f"{ENV_PATH} (file NOT found)"
        sys.exit(
            "Missing settings: " + ", ".join(missing) + f"\nExpected them in: {where}\n"
            "Copy .env.example to .env and fill in the values."
        )


check_config()

SQL_CONN_STR = os.environ["SQL_CONNECTION_STRING"]
SQL_SCHEMA = os.getenv("SQL_SCHEMA", "dbo")
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", SQL_SCHEMA):
    sys.exit(f"Invalid SQL_SCHEMA: {SQL_SCHEMA!r}")

LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

if LLM_PROVIDER == "azure":
    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
        timeout=LLM_TIMEOUT,
    )
    LLM_MODEL = os.environ["AZURE_OPENAI_DEPLOYMENT"]
elif LLM_PROVIDER == "local":
    client = OpenAI(
        base_url=os.environ["LOCAL_LLM_BASE_URL"].rstrip("/"),
        api_key=os.getenv("LOCAL_LLM_API_KEY", "not-needed"),
        timeout=LLM_TIMEOUT,
        max_retries=0,
    )
    LLM_MODEL = os.environ["LOCAL_LLM_MODEL"]
else:
    client = None
    LLM_MODEL = None

print(f"[config] LLM_PROVIDER={LLM_PROVIDER} model={LLM_MODEL} schema={SQL_SCHEMA}")

FAQ_THRESHOLD = 0.6     # share of query words that must appear in an FAQ question
MAX_CANDIDATES = 5

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "to", "of", "for", "in", "on", "at", "and",
    "or", "i", "me", "my", "we", "our", "you", "your", "it", "this", "that", "how",
    "what", "where", "which", "who", "do", "does", "can", "could", "should", "would",
    "want", "need", "please", "with", "from", "get", "find", "app", "application",
    "link", "url", "tool", "portal", "use", "there", "any", "be", "will", "am",
}


# ---------------------------------------------------------------- data types
@dataclass
class BotAnswer:
    text: str
    matched_type: str = "NONE"           # 'FAQ', 'APP' or 'NONE'
    matched_id: Optional[str] = None
    app: Optional[dict] = None           # set when an app is recommended
    suggestions: list = field(default_factory=list)  # other candidate apps


# ---------------------------------------------------------------- helpers
def tokens(text: Optional[str]) -> set:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def get_conn():
    return pyodbc.connect(SQL_CONN_STR, timeout=15)


def rows_as_dicts(cursor) -> list:
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def load_faqs(conn) -> list:
    cur = conn.cursor()
    cur.execute(
        f"SELECT faq_id, question, answer, related_app_id, category FROM {SQL_SCHEMA}.FAQs"
    )
    return rows_as_dicts(cur)


def load_apps(conn) -> list:
    cur = conn.cursor()
    cur.execute(
        f"""SELECT app_id, app_name, category, short_description, url, keywords,
                   access_notes, owner_contact
            FROM {SQL_SCHEMA}.Applications WHERE status = 'Active'"""
    )
    return rows_as_dicts(cur)


def log_query(conn, query: str, ans: BotAnswer, teams_user: Optional[str]) -> None:
    try:
        cur = conn.cursor()
        cur.execute(
            f"""INSERT INTO {SQL_SCHEMA}.QueryLog (user_query, matched_type, matched_id, teams_user)
                VALUES (?, ?, ?, ?)""",
            (query[:1000], ans.matched_type, ans.matched_id, (teams_user or "")[:200] or None),
        )
        conn.commit()
    except Exception as exc:  # logging must never break the reply
        print(f"[warn] QueryLog insert failed: {exc}")


# ---------------------------------------------------------------- matching
def match_faq(q_tokens: set, faqs: list) -> Optional[dict]:
    best, best_score = None, 0.0
    for f in faqs:
        f_tokens = tokens(f["question"])
        if not f_tokens:
            continue
        overlap = len(q_tokens & f_tokens)
        # must cover most of the query AND most of the FAQ question
        score = min(overlap / len(q_tokens), overlap / len(f_tokens))
        if score > best_score:
            best, best_score = f, score
    return best if best_score >= FAQ_THRESHOLD else None


def score_app(q_tokens: set, app: dict) -> float:
    name = tokens(app["app_name"])
    kw = tokens((app.get("keywords") or "").replace(",", " "))
    desc = tokens(app.get("short_description"))
    cat = tokens(app.get("category"))
    return (
        3.0 * len(q_tokens & name)
        + 2.0 * len(q_tokens & kw)
        + 1.0 * len(q_tokens & desc)
        + 0.5 * len(q_tokens & cat)
    )


def keyword_candidates(q_tokens: set, apps: list) -> list:
    scored = [(score_app(q_tokens, a), a) for a in apps]
    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda s: s[0], reverse=True)
    return [a for _, a in scored[:MAX_CANDIDATES]]


def llm_pick(query: str, candidates: list) -> Optional[dict]:
    """Ask the LLM to choose one candidate. Returns {'app_id', 'answer'} or None."""
    if client is None:  # LLM_PROVIDER=none -> keyword match only
        return None
    catalog = [
        {
            "app_id": a["app_id"],
            "name": a["app_name"],
            "category": a.get("category"),
            "description": a.get("short_description"),
            "keywords": a.get("keywords"),
            "access_notes": a.get("access_notes"),
        }
        for a in candidates
    ]
    system = (
        "You help Mastek employees find the right internal application. "
        "Pick the ONE application from the list that best answers the question. "
        "If none fits, use app_id null. Reply ONLY with JSON: "
        '{"app_id": "<id or null>", "answer": "<1-2 friendly sentences, no URLs>"}'
    )
    user = f"Question: {query}\n\nApplications:\n{json.dumps(catalog, ensure_ascii=False)}"
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0,
            max_tokens=250,
        )
        raw = resp.choices[0].message.content or ""
        m = re.search(r"\{.*\}", raw, re.S)
        pick = json.loads(m.group(0)) if m else None
    except Exception as exc:
        print(f"[warn] LLM call failed ({LLM_PROVIDER}), using keyword match: {exc}")
        return None
    if not isinstance(pick, dict):
        return None
    # Small local models sometimes return "null" as a string or invent an id.
    app_id = pick.get("app_id")
    if isinstance(app_id, str) and app_id.strip().lower() in {"", "null", "none"}:
        app_id = None
    if app_id is not None and app_id not in {a["app_id"] for a in candidates}:
        print(f"[warn] LLM returned unknown app_id {app_id!r}, using keyword match")
        return None
    pick["app_id"] = app_id
    return pick


# ---------------------------------------------------------------- entry point
def handle_user_query(query: str, teams_user: Optional[str] = None) -> BotAnswer:
    query = (query or "").strip()
    if not query:
        return BotAnswer(text="Ask me which app to use, e.g. *Where do I apply for leave?*")

    conn = get_conn()
    try:
        q_tokens = tokens(query)
        apps = load_apps(conn)
        apps_by_id = {a["app_id"]: a for a in apps}

        # 1. FAQ
        faq = match_faq(q_tokens, load_faqs(conn)) if q_tokens else None
        if faq:
            ans = BotAnswer(
                text=faq["answer"],
                matched_type="FAQ",
                matched_id=faq["faq_id"],
                app=apps_by_id.get(faq.get("related_app_id")),
            )
            log_query(conn, query, ans, teams_user)
            return ans

        # 2. Keyword filter
        candidates = keyword_candidates(q_tokens, apps) if q_tokens else []
        if not candidates:
            ans = BotAnswer(
                text="I couldn't find an application for that. Try different words, "
                     "or contact the IT helpdesk.",
            )
            log_query(conn, query, ans, teams_user)
            return ans

        # 3. LLM pick (fallback: top keyword match)
        pick = llm_pick(query, candidates)
        chosen = apps_by_id.get(pick.get("app_id")) if pick and pick.get("app_id") else None
        if pick and pick.get("app_id") is None and pick.get("answer"):
            ans = BotAnswer(text=pick["answer"], suggestions=candidates[:3])
        else:
            chosen = chosen or candidates[0]
            text = (pick or {}).get("answer") or (
                f"**{chosen['app_name']}** looks like the right place. "
                f"{chosen.get('short_description') or ''}".strip()
            )
            ans = BotAnswer(
                text=text,
                matched_type="APP",
                matched_id=chosen["app_id"],
                app=chosen,
                suggestions=[c for c in candidates if c["app_id"] != chosen["app_id"]][:2],
            )
        log_query(conn, query, ans, teams_user)
        return ans
    finally:
        conn.close()


def build_adaptive_card(ans: BotAnswer) -> dict:
    """Adaptive Card for Teams: answer text + Open App button + alternatives."""
    body = [{"type": "TextBlock", "text": ans.text, "wrap": True}]
    actions = []
    if ans.app:
        a = ans.app
        body.append({"type": "TextBlock", "text": a["app_name"], "weight": "Bolder",
                     "size": "Medium", "spacing": "Medium"})
        facts = [{"title": "Category", "value": a.get("category") or "-"}]
        if a.get("access_notes"):
            facts.append({"title": "Access", "value": a["access_notes"]})
        if a.get("owner_contact"):
            facts.append({"title": "Contact", "value": a["owner_contact"]})
        body.append({"type": "FactSet", "facts": facts})
        actions.append({"type": "Action.OpenUrl", "title": f"Open {a['app_name']}",
                        "url": a["url"]})
    for s in ans.suggestions:
        actions.append({"type": "Action.OpenUrl", "title": s["app_name"], "url": s["url"]})
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": actions,
    }
