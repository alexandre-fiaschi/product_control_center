#!/usr/bin/env python3
"""
Jira Connection Dry Run
Tests API connectivity, validates project key, lists issue types,
fetches create metadata, and builds a sample payload without creating anything.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN_NO_SCOPES")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")

# ---------- helpers ----------

def jira_get(path):
    """GET request to Jira REST API v3 with Basic Auth (email:classic_token)."""
    url = f"{JIRA_BASE_URL}/rest/api/3{path}"
    resp = requests.get(url, auth=(JIRA_EMAIL, JIRA_API_TOKEN), headers={"Accept": "application/json"})
    return resp

def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

# ---------- pre-flight checks ----------

missing = []
if not JIRA_BASE_URL: missing.append("JIRA_BASE_URL")
if not JIRA_EMAIL: missing.append("JIRA_EMAIL")
if not JIRA_API_TOKEN: missing.append("JIRA_API_TOKEN")
if not JIRA_PROJECT_KEY: missing.append("JIRA_PROJECT_KEY")

if missing:
    print(f"ERROR: Missing env vars: {', '.join(missing)}")
    print("Add them to .env and retry.")
    sys.exit(1)

print(f"Jira URL:     {JIRA_BASE_URL}")
print(f"Email:        {JIRA_EMAIL}")
print(f"Project Key:  {JIRA_PROJECT_KEY}")

# ---------- Step 1: Test connection ----------

separator("Step 1: Test Connection (GET /myself)")

resp = jira_get("/myself")
if resp.status_code != 200:
    print(f"FAILED — HTTP {resp.status_code}")
    print(resp.text[:500])
    sys.exit(1)

me = resp.json()
print(f"Authenticated as: {me.get('displayName')} ({me.get('emailAddress')})")
print(f"Account ID:       {me.get('accountId')}")

# ---------- Step 2: Validate project ----------

separator("Step 2: Validate Project")

resp = jira_get(f"/project/{JIRA_PROJECT_KEY}")
if resp.status_code != 200:
    print(f"FAILED — HTTP {resp.status_code}")
    print(resp.text[:500])
    print("\nCheck the project key. Try browsing: " + f"{JIRA_BASE_URL}/rest/api/3/project")
    sys.exit(1)

project = resp.json()
print(f"Project found:  {project.get('name')}")
print(f"Key:            {project.get('key')}")
print(f"ID:             {project.get('id')}")
print(f"Style:          {project.get('style')}")

# ---------- Step 3: List issue types for this project ----------

separator("Step 3: Issue Types for Project")

resp = jira_get(f"/project/{JIRA_PROJECT_KEY}/statuses")
if resp.status_code == 200:
    for item in resp.json():
        it = item.get("name", "?")
        statuses = [s["name"] for s in item.get("statuses", [])]
        print(f"  Issue Type: {it}")
        print(f"    Statuses: {', '.join(statuses)}")
        print()
else:
    print(f"Could not fetch statuses — HTTP {resp.status_code}")

# Also get issue types directly
resp = jira_get(f"/issuetype/project?projectId={project.get('id')}")
issue_types = []
if resp.status_code == 200:
    issue_types = resp.json()
    print("Available issue types:")
    for it in issue_types:
        scope = it.get("scope", {}).get("type", "global")
        print(f"  - {it['name']} (id={it['id']}, subtask={it.get('subtask', False)}, scope={scope})")
else:
    # Fallback: get all issue types
    resp = jira_get("/issuetype")
    if resp.status_code == 200:
        issue_types = resp.json()
        print("All issue types (not project-filtered):")
        for it in issue_types:
            print(f"  - {it['name']} (id={it['id']}, subtask={it.get('subtask', False)})")

# ---------- Step 4: Get create metadata ----------

separator("Step 4: Create Metadata (Required Fields)")

# Pick the first non-subtask issue type for inspection
target_type = None
for it in issue_types:
    if not it.get("subtask", False):
        target_type = it
        break

if target_type:
    print(f"Inspecting fields for issue type: {target_type['name']} (id={target_type['id']})")
    print()

    resp = jira_get(f"/issue/createmeta/{JIRA_PROJECT_KEY}/issuetypes/{target_type['id']}")
    if resp.status_code == 200:
        fields = resp.json().get("values", resp.json().get("fields", []))
        print(f"Fields ({len(fields)} total):")
        print()

        required_fields = []
        optional_fields = []

        for f in fields:
            # Handle both list-of-dicts and dict-of-dicts formats
            if isinstance(f, str):
                field = fields[f]
                field_id = f
            else:
                field = f
                field_id = f.get("fieldId", f.get("key", "?"))

            name = field.get("name", "?")
            required = field.get("required", False)

            if required:
                required_fields.append((field_id, name, field))
            else:
                optional_fields.append((field_id, name, field))

        print("REQUIRED fields:")
        for fid, name, field in required_fields:
            allowed = field.get("allowedValues", [])
            schema = field.get("schema", {})
            print(f"  * {name} ({fid})")
            if schema:
                print(f"    type: {schema.get('type', '?')}, system: {schema.get('system', '-')}")
            if allowed:
                vals = [v.get("name", v.get("value", str(v.get("id", "?")))) for v in allowed[:10]]
                print(f"    allowed: {', '.join(vals)}")
                if len(allowed) > 10:
                    print(f"    ... and {len(allowed) - 10} more")
            print()

        print(f"\nOPTIONAL fields ({len(optional_fields)} total):")
        for fid, name, _ in optional_fields[:15]:
            print(f"  - {name} ({fid})")
        if len(optional_fields) > 15:
            print(f"  ... and {len(optional_fields) - 15} more")
    else:
        print(f"Could not fetch create metadata — HTTP {resp.status_code}")
        print(resp.text[:500])
else:
    print("No non-subtask issue type found to inspect.")

# ---------- Step 5: Dry-run payload ----------

separator("Step 5: Dry-Run Payload (NOT sending)")

# --- Sample patch for dry run ---
sample_patch_id = "8.1.11.0"
sample_version = "8.1.11"
is_new_folder = True  # first patch for this version folder

release_name = f"Version {sample_version}"
new_or_existing = "new" if is_new_folder else "existing"
create_update = "New CAE Portal Release" if is_new_folder else "Existing CAE Portal Release"

description_text = (
    f"Hi Team,\n\n"
    f"I have this binaries for the release {sample_version} that should all be added "
    f"in a {new_or_existing} folder '{release_name}'.\n\n"
    f"Please contact me for any questions you may have.\n\n"
    f"Thank you very much,"
)

def text_to_adf(text):
    """Convert plain text to Atlassian Document Format, preserving line breaks."""
    content = []
    for line in text.split("\n"):
        if line:
            content.append({"type": "text", "text": line})
        content.append({"type": "hardBreak"})
    # Remove trailing hardBreak
    if content and content[-1]["type"] == "hardBreak":
        content.pop()
    return {
        "version": 1,
        "type": "doc",
        "content": [{"type": "paragraph", "content": content}]
    }

payload = {
    "fields": {
        "project": {"key": JIRA_PROJECT_KEY},
        "issuetype": {"id": "10163"},
        "summary": f"Add Release Version v{sample_patch_id}",
        "description": text_to_adf(description_text),
        # Client (required)
        "customfield_10328": [{"value": "Flightscape"}],
        # Environment (required)
        "customfield_10538": {"value": "All the three"},
        # Product Name (required)
        "customfield_10562": "CAE\u00ae Operations Communication Manager",
        # Release Name (required)
        "customfield_10563": release_name,
        # Release Type (required)
        "customfield_10616": {"value": "Version"},
        # Release Approval (required)
        "customfield_10617": {"value": "Users should not request approval to access or download files on this release"},
        # Create/Update/Remove (required)
        "customfield_10618": {"value": create_update},
    }
}

print("Sample payload (would be sent to POST /rest/api/3/issue):")
print()
print(json.dumps(payload, indent=2, ensure_ascii=False))
print()
print(f"  Summary:          Add Release Version v{sample_patch_id}")
print(f"  Release Name:     {release_name}")
print(f"  New/Existing:     {create_update}")
print(f"  Client:           Flightscape")
print(f"  Environment:      All the three")

# ---------- Step 6: Attachment simulation ----------

separator("Step 6: Attachment Simulation (NOT sending)")

sample_zip = f"{sample_patch_id}.zip"
print(f"After ticket creation + approval, binaries would be zipped and attached.")
print(f"  Zip file:     {sample_zip}")
print(f"  API endpoint: POST /rest/api/3/issue/{{ticket_key}}/attachments")
print(f"  Header:       X-Atlassian-Token: no-check")
print(f"  Content-Type: multipart/form-data")
print()
print(f"  curl equivalent:")
print(f'  curl -u {JIRA_EMAIL}:$TOKEN \\')
print(f'    -X POST \\')
print(f'    -H "X-Atlassian-Token: no-check" \\')
print(f'    -F "file=@{sample_zip}" \\')
print(f'    {JIRA_BASE_URL}/rest/api/3/issue/CFSSOCP-XXX/attachments')
print()
print("--- DRY RUN COMPLETE — no ticket was created, no file was attached ---")
