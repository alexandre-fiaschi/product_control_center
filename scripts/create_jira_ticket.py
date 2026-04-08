#!/usr/bin/env python3
"""
Create a real Jira ticket for a patch and attach a test zip file.

Usage:
    python scripts/create_jira_ticket.py --patch-id 8.1.11.0
"""

import argparse
import io
import json
import os
import sys
import zipfile
from pathlib import Path

from dotenv import load_dotenv
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN_NO_SCOPES")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "CFSSOCP")

AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)

# ---------- helpers ----------

def jira_get(path):
    url = f"{JIRA_BASE_URL}/rest/api/3{path}"
    return requests.get(url, auth=AUTH, headers={"Accept": "application/json"})

def jira_post(path, json_data=None, **kwargs):
    url = f"{JIRA_BASE_URL}/rest/api/3{path}"
    return requests.post(url, auth=AUTH, json=json_data,
                         headers={"Accept": "application/json"}, **kwargs)

def text_to_adf(text):
    """Convert plain text to Atlassian Document Format, preserving line breaks."""
    content = []
    for line in text.split("\n"):
        if line:
            content.append({"type": "text", "text": line})
        content.append({"type": "hardBreak"})
    if content and content[-1]["type"] == "hardBreak":
        content.pop()
    return {
        "version": 1,
        "type": "doc",
        "content": [{"type": "paragraph", "content": content}]
    }

def find_patch(patch_id):
    """Look up a patch across all state tracker files. Returns (product_id, version, patch_data) or None."""
    state_dir = PROJECT_ROOT / "state" / "patches"
    for tracker_file in state_dir.glob("*.json"):
        with open(tracker_file) as f:
            tracker = json.load(f)
        for version_id, version_data in tracker.get("versions", {}).items():
            patches = version_data.get("patches", {})
            if patch_id in patches:
                return tracker["product_id"], version_id, patches[patch_id]
    return None

def check_existing_version(version):
    """Query Jira to see if a ticket already exists for this version folder."""
    jql = f'project = {JIRA_PROJECT_KEY} AND cf[10563] = "Version {version}"'
    resp = jira_post("/search/jql", json_data={"jql": jql, "maxResults": 1, "fields": ["summary", "customfield_10563"]})
    if resp.status_code == 200:
        return resp.json().get("total", 0) > 0
    print(f"  WARNING: JQL search failed (HTTP {resp.status_code}), assuming new folder")
    return False

# ---------- main ----------

def main():
    parser = argparse.ArgumentParser(description="Create a Jira ticket for a patch")
    parser.add_argument("--patch-id", default="8.1.11.0", help="Patch ID (e.g., 8.1.11.0)")
    args = parser.parse_args()

    patch_id = args.patch_id

    # Pre-flight
    missing = []
    if not JIRA_BASE_URL: missing.append("JIRA_BASE_URL")
    if not JIRA_EMAIL: missing.append("JIRA_EMAIL")
    if not JIRA_API_TOKEN: missing.append("JIRA_API_TOKEN_NO_SCOPES")
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    # Step 1: Verify connection
    print("Step 1: Testing Jira connection...")
    resp = jira_get("/myself")
    if resp.status_code != 200:
        print(f"FAILED — HTTP {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)
    me = resp.json()
    print(f"  Authenticated as: {me.get('displayName')}")

    # Step 2: Find the patch in state
    print(f"\nStep 2: Looking up patch {patch_id}...")
    result = find_patch(patch_id)
    if not result:
        print(f"  ERROR: Patch {patch_id} not found in any state tracker file")
        sys.exit(1)
    product_id, version, patch_data = result
    print(f"  Found: product={product_id}, version={version}, binaries={patch_data['binaries']['status']}, release_notes={patch_data['release_notes']['status']}")

    # Step 3: New or existing folder?
    print(f"\nStep 3: Checking if version folder '{version}' already exists in Jira...")
    is_existing = check_existing_version(version)
    new_or_existing = "existing" if is_existing else "new"
    create_update = "Existing CAE Portal Release" if is_existing else "New CAE Portal Release"
    print(f"  Result: {create_update}")

    # Step 4: Build payload
    release_name = f"Version {version}"
    description_text = (
        f"Hi Team,\n\n"
        f"I have this binaries for the release {version} that should all be added "
        f"in a {new_or_existing} folder '{release_name}'.\n\n"
        f"Please contact me for any questions you may have.\n\n"
        f"Thank you very much,"
    )

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "issuetype": {"id": "10163"},
            "summary": f"Add Release Version v{patch_id}",
            "description": text_to_adf(description_text),
            "customfield_10328": [{"value": "Flightscape"}],
            "customfield_10538": {"value": "All the three"},
            "customfield_10562": "CAE\u00ae Operations Communication Manager",
            "customfield_10563": release_name,
            "customfield_10616": {"value": "Version"},
            "customfield_10617": {"value": "Users should not request approval to access or download files on this release"},
            "customfield_10618": {"value": create_update},
        }
    }

    print(f"\nStep 4: Creating Jira ticket...")
    print(f"  Summary:      Add Release Version v{patch_id}")
    print(f"  Release Name: {release_name}")
    print(f"  Folder:       {create_update}")

    resp = jira_post("/issue", json_data=payload)
    if resp.status_code not in (200, 201):
        print(f"\n  FAILED — HTTP {resp.status_code}")
        print(f"  Response: {resp.text[:1000]}")
        sys.exit(1)

    ticket = resp.json()
    ticket_key = ticket["key"]
    ticket_url = f"{JIRA_BASE_URL}/browse/{ticket_key}"
    print(f"\n  TICKET CREATED: {ticket_key}")
    print(f"  URL: {ticket_url}")

    # Step 5: Upload test attachment
    print(f"\nStep 5: Uploading test attachment...")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("test_readme.txt", f"Test attachment for patch {patch_id}\nThis is a validation file.")
    zip_buffer.seek(0)

    attach_url = f"{JIRA_BASE_URL}/rest/api/3/issue/{ticket_key}/attachments"
    attach_resp = requests.post(
        attach_url,
        auth=AUTH,
        headers={"X-Atlassian-Token": "no-check"},
        files={"file": (f"{patch_id}.zip", zip_buffer, "application/zip")},
    )

    if attach_resp.status_code in (200, 201):
        print(f"  Attachment uploaded: {patch_id}.zip")
    else:
        print(f"  Attachment FAILED — HTTP {attach_resp.status_code}")
        print(f"  Response: {attach_resp.text[:500]}")

    # Done
    print(f"\n{'='*60}")
    print(f"  DONE — Ticket ready for inspection")
    print(f"  {ticket_url}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
