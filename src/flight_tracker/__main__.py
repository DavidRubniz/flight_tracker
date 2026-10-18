"""Entry point: ``uv run flight-tracker`` (or ``python -m flight_tracker``)."""

from __future__ import annotations

import argparse
import logging
import threading
import webbrowser

import uvicorn

from flight_tracker.api import create_app
from flight_tracker.config import get_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Flight price tracker from Israel")
    parser.add_argument("--no-browser", action="store_true", help="don't open the UI automatically")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    config = get_config()
    url = f"http://{config.app_host}:{config.app_port}"
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(config), host=config.app_host, port=config.app_port, log_level="info")


if __name__ == "__main__":
    main()
