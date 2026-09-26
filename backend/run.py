import asyncio
import sys

# Must run before uvicorn creates its event loop (asyncio.run() picks up
# whatever policy is active at that moment) — Playwright needs Proactor on
# Windows to launch subprocesses; uvicorn's default there is Selector, which
# raises NotImplementedError as soon as async_playwright() tries to spawn
# the browser process. This is why `uvicorn main:app` on the CLI can't be
# patched from within main.py: by the time main.py is imported, uvicorn's
# own asyncio.run() has already created the loop with the wrong policy.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
