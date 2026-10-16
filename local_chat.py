"""
Chat with the bot in your terminal - no server, no Teams.
    python local_chat.py
Type 'exit' to quit.
"""
from bot_logic import handle_user_query

print("App Navigator - local test. Type 'exit' to quit.\n")
while True:
    try:
        q = input("You: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if q.lower() in {"exit", "quit"}:
        break
    ans = handle_user_query(q, teams_user="local-test")
    print(f"\nBot [{ans.matched_type} {ans.matched_id or ''}]: {ans.text}")
    if ans.app:
        print(f"  -> {ans.app['app_name']}: {ans.app['url']}")
    for s in ans.suggestions:
        print(f"  also: {s['app_name']}: {s['url']}")
    print()
