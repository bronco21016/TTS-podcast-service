#!/usr/bin/env python3
"""
Run this on a machine with a display (laptop/desktop) to authenticate with X.com.
Saves a session file you can then SCP to the server.

Setup (one time):
    pip install playwright
    playwright install chromium

Usage:
    python auth_x_helper.py
    scp x_session.json user@yourserver:/home/admin/claude/TTS_service/
"""
from playwright.sync_api import sync_playwright

OUTPUT = "x_session.json"

print("Opening browser — log into X.com, then come back here.")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto("https://x.com/login")
    input("\nPress Enter once you're logged in and the feed has loaded... ")
    ctx.storage_state(path=OUTPUT)
    browser.close()

print(f"\nSession saved to {OUTPUT}")
print(f"\nCopy to server:")
print(f"  scp {OUTPUT} admin@192.168.2.15:/home/admin/claude/TTS_service/")
