#!/usr/bin/env python3
"""
Convert cookies exported from Cookie-Editor browser extension into
a Playwright session file, then SCP it to the server.

Setup:
    1. Install Cookie-Editor extension in Chrome or Firefox
    2. Go to x.com while logged in
    3. Open Cookie-Editor → Export → "Export as JSON" → paste into x_cookies.json
    4. Run: python auth_x_helper.py x_cookies.json

Then copy to server:
    scp x_session.json admin@192.168.2.15:/home/admin/claude/TTS_service/
"""
import json
import sys
from pathlib import Path

SAMSITE_MAP = {"no_restriction": "None", "lax": "Lax", "strict": "Strict", "unspecified": "Lax"}


def convert(input_path: str, output_path: str = "x_session.json"):
    raw = json.loads(Path(input_path).read_text())

    cookies = []
    for c in raw:
        same_site_raw = (c.get("sameSite") or "lax").lower()
        cookies.append({
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ".x.com"),
            "path": c.get("path", "/"),
            "expires": c.get("expirationDate", -1),
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "sameSite": SAMSITE_MAP.get(same_site_raw, "Lax"),
        })

    storage_state = {"cookies": cookies, "origins": []}
    Path(output_path).write_text(json.dumps(storage_state, indent=2))
    print(f"Converted {len(cookies)} cookies → {output_path}")
    print(f"\nCopy to server:")
    print(f"  scp {output_path} admin@192.168.2.15:/home/admin/claude/TTS_service/")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python auth_x_helper.py x_cookies.json")
        sys.exit(1)
    convert(sys.argv[1])
