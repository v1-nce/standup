import argparse
import threading
import webbrowser

import uvicorn

from standup.api.app import WEB
from standup.core import llm

UNCONFIGURED = """Standup needs a model before it can do anything. Three ways:

  1. Subscribe   - sign in, we hold the key
  2. Your key    - ANTHROPIC_API_KEY or GEMINI_API_KEY in ~/.standup/.env
  3. Local model - LLM_BASE_URL in the same file

Indexing a project works without any of them; only writing slides needs one."""


def main() -> None:
    parser = argparse.ArgumentParser(prog="standup", description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    options = parser.parse_args()

    if llm.active_provider() is None:
        print(UNCONFIGURED)

    address = f"http://127.0.0.1:{options.port}"
    if not WEB.is_dir():
        print(f"No GUI built, so {address} serves the API only. Build it with: cd ui && npm run build")
    elif not options.no_browser:
        # Opens browser tab for GUI
        threading.Timer(1.0, webbrowser.open, [address]).start()

    uvicorn.run("standup.api.app:app", host="127.0.0.1", port=options.port)
