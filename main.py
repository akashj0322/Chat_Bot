"""
App Navigator Bot - FastAPI server.

Endpoints:
  GET  /health         -> quick liveness check
  POST /ask            -> {"query": "..."}  plain JSON test endpoint (no Teams needed)
  POST /api/messages   -> Bot Framework endpoint (Teams / Bot Framework Emulator)

Run locally:
    python main.py            (defaults to http://127.0.0.1:8024)
"""
import asyncio
import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from bot_logic import build_adaptive_card, handle_user_query  # loads .env

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    CardFactory,
    MessageFactory,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes

APP_ID = os.getenv("MicrosoftAppId", "")
APP_PASSWORD = os.getenv("MicrosoftAppPassword", "")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8024"))

adapter = BotFrameworkAdapter(BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD))


async def on_error(context: TurnContext, error: Exception):
    print(f"[error] {error}")
    await context.send_activity("Sorry, something went wrong. Please try again.")

adapter.on_turn_error = on_error

app = FastAPI(title="App Navigator")

WELCOME = ("Hi! I'm ** App Navigator**. Ask me where to do something, e.g. "
           "*How do I apply for leave?* or *Where do I submit travel requests?*")


class AskRequest(BaseModel):
    query: str
    user: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
async def ask(req: AskRequest):
    ans = await asyncio.to_thread(handle_user_query, req.query, req.user)
    return {
        "text": ans.text,
        "matched_type": ans.matched_type,
        "matched_id": ans.matched_id,
        "app": ans.app,
        "suggestions": [{"app_name": s["app_name"], "url": s["url"]} for s in ans.suggestions],
    }


async def bot_turn(context: TurnContext):
    act = context.activity
    if act.type == ActivityTypes.message:
        text = TurnContext.remove_recipient_mention(act) if act.entities else act.text
        user = act.from_property.name if act.from_property else None
        ans = await asyncio.to_thread(handle_user_query, (text or "").strip(), user)
        card = CardFactory.adaptive_card(build_adaptive_card(ans))
        await context.send_activity(MessageFactory.attachment(card))
    elif act.type == ActivityTypes.conversation_update:
        for m in act.members_added or []:
            if m.id != act.recipient.id:
                await context.send_activity(WELCOME)


@app.post("/api/messages")
async def messages(req: Request):
    if "application/json" not in req.headers.get("Content-Type", ""):
        return Response(status_code=415)
    activity = Activity().deserialize(await req.json())
    auth_header = req.headers.get("Authorization", "")
    response = await adapter.process_activity(activity, auth_header, bot_turn)
    if response:
        return JSONResponse(content=response.body, status_code=response.status)
    return Response(status_code=201)


if __name__ == "__main__":
    print(f"App Navigator running on http://{HOST}:{PORT}  (Teams endpoint: /api/messages)")
    uvicorn.run(app, host=HOST, port=PORT)
