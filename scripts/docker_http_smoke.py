#!/usr/bin/env python3
"""Check the Streamable HTTP MCP endpoint using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def initialize(url: str, token: str, timeout: float) -> tuple[int, str]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "ocular-audio-container-health", "version": "1.0.0"},
        },
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--token", default=os.environ.get("OCULAR_AUDIO_MCP_AUTH_TOKEN", ""))
    parser.add_argument("--attempts", type=int, default=30)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    if args.attempts < 1 or args.interval < 0:
        parser.error("--attempts must be positive and --interval cannot be negative")

    last_error = "container did not become ready"
    for attempt in range(args.attempts):
        try:
            status, body = initialize(args.url, args.token, timeout=5)
            if status == 200 and "OcularAudio Server" in body:
                print("MCP initialize succeeded.")
                return 0
            last_error = f"unexpected HTTP {status}: {body[:1000]}"
        except (URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        if attempt + 1 < args.attempts:
            time.sleep(args.interval)

    raise SystemExit(f"MCP readiness check failed: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())
