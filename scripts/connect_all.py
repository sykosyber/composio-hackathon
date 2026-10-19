import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from composio import Composio
from src import config
tks = sys.argv[1].split(",") if len(sys.argv) > 1 else ["gmail","googledocs","googlecalendar","slack"]
c = Composio(api_key=config.COMPOSIO_API_KEY)
s = c.create(user_id=config.COMPOSIO_USER_ID, toolkits=tks)
reqs = {}
for tk in tks:
    r = s.authorize(tk); reqs[tk] = r
    print(f"LINK {tk}: {r.redirect_url}", flush=True)
for tk, r in reqs.items():
    try:
        a = r.wait_for_connection(timeout=900); print(f"CONNECTED {tk}: {a.id}", flush=True)
    except Exception as e:
        print(f"FAILED {tk}: {e}", flush=True)
