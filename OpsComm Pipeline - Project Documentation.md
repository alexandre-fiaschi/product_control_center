# OpsComm Docs & Binaries Pipeline

**Project Documentation**

Version 1.0 | April 03, 2026

*Confidential and Proprietary — CAE Inc.*

---

## Table of Contents

1. Executive Summary
2. Pipeline Overview
3. Stage 1 — SFTP Ingestion & Structure Preservation
4. Stage 2 — Documentation Template Conversion
5. Stage 3 — Review & Approval
6. Stage 4 — Jira Task Creation & Community Portal Publishing
7. Stage 5 — Future: Automated Jira Integration via Atlassian MCP
8. Folder Structure & State Tracking
9. Version & Patch Naming Conventions
10. Product Lines & SFTP Structure
11. Atlassian MCP Integration Reference
12. Next Steps & Roadmap

---

## 1. Executive Summary

This document describes the OpsComm Docs & Binaries Pipeline, an internal workflow system designed to automate the ingestion, processing, review, and publishing of software releases for the Flightscape product family. The pipeline receives files from an SFTP server, separates application binaries from documentation, applies the CAE corporate template to raw documentation, stages everything for human review, and ultimately creates Jira tasks for the DevOps team to publish both binaries and templated documentation to the customer-facing developer portal.

The pipeline supports multiple product lines (Flightscape versioned releases, ACARS V8, etc.) and understands version-patch bundling — for example, sub-patches 7.3.27.0 through 7.3.27.8 are automatically grouped as a single "Version 7.3.27" release.

*Currently, the Jira integration is not yet active due to pending admin access. Files are staged in an approved folder for manual Jira ticket creation. Once Atlassian MCP integration is enabled (see Section 7 and 11), the pipeline will automatically create Jira tasks per approved version.*

---

## 2. Pipeline Overview

The pipeline consists of five stages, with Stage 5 being a future enhancement:

**Pipeline Flow:**

```
SFTP Server → [Stage 1: Ingestion & Structure Preservation] → Each patch's folders preserved as-is
            → If DOC/ exists: also route to [Stage 2: Template Conversion]
            → [Stage 3: Human Review & Approval (per-patch)]
            → [Stage 4: Approved Folders / Jira Task Creation]
            → [Stage 5 (Future): Automated Jira Task Creation via Atlassian MCP]
```

### Key Design Principles

- **Patch-centric:** each sub-patch is an independent deliverable tracked through the full pipeline
- **Structure-preserving:** entire folder structure of each patch is preserved as-is from SFTP
- **Product-agnostic:** supports Flightscape, ACARS, and future product lines from the same SFTP
- **Template-driven:** documentation is reformatted using the CAE corporate .docx template
- **Human-in-the-loop:** all patches pass through manual approval before publishing
- **Jira-ready:** designed so that Jira automation can be plugged in without changing earlier stages
- **Full audit trail:** JSON state tracker records every patch, timestamp, file, and approval

---

## 3. Stage 1 — SFTP Ingestion & Structure Preservation

A scheduled script connects to the SFTP server, discovers new patch folders, downloads their contents, and preserves the entire folder structure of each patch as-is. If a DOC/ subfolder exists within a patch, those documents are additionally routed to template conversion.

### SFTP Folder Structure

The SFTP organizes files by product line, version, and patch. Each patch is an independent deliverable. Folder structures vary by product line.

**Example ACARS structure (hierarchical):**

```
ACARS_V8_1/                          ← product line
  ACARS_V8_1_10/                     ← version 8.1.10
    8.1.10.0/                        ← patch (independent deliverable)
      Binaries/
      Script/
      Web Applications/
      Web Services/
    8.1.10.1/                        ← another patch
  ACARS_V8_1_11/                     ← version 8.1.11
    8.1.11.0/
    8.1.11.2/

ACARS_V8_0/
  ...
```

**Example Flightscape structure (flat):**

```
Flightscape_7_3/
  7_3_27_0/                          ← patch folder (no parent version folder)
    WEBAPPS/
    DOC/
  7_3_27_5/                          ← another patch
    WEBAPPS/
    DOC/
  7_3_28_0/
    WEBAPPS/
    (note: DOC/ may or may not be present)
```

### Folder Preservation & Classification

Everything inside a patch folder is preserved as-is from the SFTP. Known subfolder names include: Binaries, Script, Scripts, Web Applications, Web Services, WEBAPPS, DOC.

**File routing:**

- All files in the patch folder are copied and preserved in the pipeline
- If a DOC/ subfolder exists, those files additionally go through template conversion
- Templated docs replace the originals in the output stage

### Patch Tracking & Grouping

The ingestion script parses patch folder names using the naming convention (e.g., `7_3_27_5` or `8.1.11.0`) to extract the version and patch identifiers. Patches are tracked individually throughout the pipeline. The state tracker records each patch separately, and approval/Jira stages operate on a per-patch basis.

---

## 4. Stage 2 — Documentation Template Conversion

Raw documentation files from the SFTP arrive without CAE branding. This stage extracts the content from each source document (paragraphs, headings, tables, images) and inserts it into the CAE corporate template, producing a polished, branded document.

### Conversion Rules

- Source document headers and footers are **DISCARDED** — only body content is used
- All text content is preserved exactly as-is (no rewording or summarization)
- Images are preserved at their original dimensions
- The CAE template provides: branded header with logo, branded footer with confidentiality notice, page numbering, section reference in footer, corporate color scheme and fonts (Red Hat Display)

### Template Details

**Template file:** `Flightscape-English-External Business Document.docx`

- Header (regular pages): CAE/Flightscape logo
- Header (first page): Dark background cover page with title area
- Footer: SUBJECT field | STYLEREF Heading 1 | "Business Name Document" | Page number | "Confidential and Proprietary CAE Inc."
- Fonts: Red Hat Display for headings and footer, default theme font for body
- Color palette: Navy (#06103D) for headings, purple (#704DFF) as accent

### Supported Input Formats

The primary input format is .docx, which provides the best fidelity for content extraction. PDF extraction is possible but with lower fidelity, especially for complex layouts, tables, and embedded images. The converter is built around .docx first, with PDF as a future fallback.

---

## 5. Stage 3 — Review & Approval

After processing, each patch is staged for human review. The reviewer (currently Alex) inspects the templated documentation (if present) and the patch contents before approving it for publication.

### Review Process

1. Open the patch folder under `patches/<PRODUCT>/<PATCH_ID>/processed/`
2. Review templated docs (if present): open each .docx file in Word to verify formatting, content integrity, and image sizing
3. Inspect patch structure: verify all expected subfolders (Binaries, Script, etc.) and files are present
4. If everything looks correct, approve the patch (move files to approved/ or trigger approval in state tracker)
5. If issues are found, flag them for re-processing or manual correction

### Approval Scope

Each patch is approved independently. For example, for ACARS_V8_1_11, patches 8.1.11.0 and 8.1.11.2 are each reviewed and approved separately. It is possible to have multiple patches pending review at once from different product lines or versions.

---

## 6. Stage 4 — Jira Task Creation & Community Portal Publishing

Once a version is approved, a Jira task is created for the DevOps team to publish the files to the customer-facing Community Portal. Today this is done manually; it will be automated via Atlassian MCP once admin access is obtained.

### Jira Work Item Form

Jira tasks use the issue type "Release notes, documents & binaries" (id=`10163`) in the CFS-ServiceOps-CommPortal project (key: `CFSSOCP`, id: `10008`). Authentication uses a classic API token with Basic Auth against `https://caeglobal.atlassian.net`.

**Required fields (confirmed via createmeta API, 2026-04-03):**

| Field | Field ID | Value (Binaries) |
|-------|----------|-------------------|
| **Project** | `project` | `{"key": "CFSSOCP"}` |
| **Issue Type** | `issuetype` | `{"id": "10163"}` |
| **Summary** | `summary` | `"Add Release Version v{patch_id}"` |
| **Client** | `customfield_10328` | `[{"value": "Flightscape"}]` |
| **Environment** | `customfield_10538` | `{"value": "All the three"}` |
| **Product Name** | `customfield_10562` | `"CAE® Operations Communication Manager"` |
| **Release Name** | `customfield_10563` | `"Version {major.minor.patch}"` (e.g., "Version 8.1.11") |
| **Release Type** | `customfield_10616` | `{"value": "Version"}` |
| **Release Approval** | `customfield_10617` | `{"value": "Users should not request approval to access or download files on this release"}` |
| **Create/Update/Remove** | `customfield_10618` | `{"value": "New CAE Portal Release"}` or `{"value": "Existing CAE Portal Release"}` |

**Optional fields used:**
- **Description** (`description`): ADF format — see description template below
- **Attachment** (`attachment`): Zipped binaries uploaded after ticket creation

### Description Template (Binaries)

```
Hi Team,

I have this binaries for the release {version} that should all be added in a [new/existing] folder '{Release Name}'.

Please contact me for any questions you may have.

Thank you very much,
```

- "new" + "New CAE Portal Release" → first patch creating a new version folder
- "existing" + "Existing CAE Portal Release" → adding to an already-existing version folder

### Attachment Workflow

Binaries are attached **after** ticket creation (not at creation time):

1. Approved patch binaries are zipped (e.g., `8.1.11.0.zip`)
2. Upload via `POST /rest/api/3/issue/{ticket_key}/attachments`
3. Requires header: `X-Atlassian-Token: no-check`
4. Content-Type: `multipart/form-data`

### Jira Task Structure Per Version

Each SFTP version folder (e.g., `ACARS_V8_1_11` = version 8.1.11) generates **one Jira task**. All sub-patches within that version (8.1.11.0, 8.1.11.2, etc.) are included in the same task. When new sub-patches arrive later for an existing version, the same ticket is updated with the new files.

**Example Jira task for version 8.1.13:**

```
Task:         Add Release Version v8.1.13
Space:        CFS-ServiceOps-CommPortal
Product Name: CAE® Operations Communication Manager
Release Name: Version v8.1.13
Release type: Version
Contents:     binaries + release notes for all sub-patches (8.1.13.0, 8.1.13.2, etc.)
```

### Community Portal Naming Convention

The Community Portal (communityportal.flightservices.cae.com) supports one level of folder depth. Each version gets a single folder, and all sub-patches are listed as items inside it.

**Portal folder name format:**

### **Version v{MAJOR}.{MINOR}.{PATCH}**

The Release type is always "Version" because each SFTP version folder (ACARS_V8_1_11, ACARS_V8_1_12, etc.) represents a distinct version. The sub-patches inside (.0, .2, etc.) are individual items within that folder, not separate folders.

**Portal structure example:**

```
CAE® Operations Communication Manager
  ├─ Version v8.1.13                            ← portal folder (= SFTP ACARS_V8_1_13)
  │    ├─ Patch 8.1.13.0 OpsComm CAE            (Downloadable Application)
  │    ├─ Patch 8.1.13.2 OpsComm CAE            (Downloadable Application)
  │    ├─ Release note 8.1.13.0 OpsComm CAE     (Release Notes)
  │    └─ Release note 8.1.13.2 OpsComm CAE     (Release Notes)
  ├─ Version v8.1.12
  ├─ Version v8.1.11
  │    ├─ Patch 8.1.11.0 OpsComm CAE            (Downloadable Application)
  │    ├─ Patch 8.1.11.2 OpsComm CAE            (Downloadable Application)
  │    ├─ Release note 8.1.11.0 OpsComm CAE     (Release Notes)
  │    └─ Release note 8.1.11.2 OpsComm CAE     (Release Notes)
  ├─ Version v8.0.28
  ├─ Version v8.0.27
  ├─ Version v7.3.27
  ├─ Version v7.3.26
  └─ Version v7.3.25
       ├─ Patch 7.3.25.0 OpsComm CAE            (Downloadable Application)
       ├─ Patch 7.3.25.1 OpsComm CAE            (Downloadable Application)
       ├─ Patch 7.3.25.2 OpsComm CAE            (Downloadable Application)
       ├─ Release note 7.3.25.0 OpsComm CAE     (Release Notes)
       ├─ Release note 7.3.25.1 OpsComm CAE     (Release Notes)
       └─ Release note 7.3.25.2 OpsComm CAE     (Release Notes)
```

#### Naming Rules

1. Portal folder name: always "Version v{X.Y.Z}" — consistent, sortable, always with "v" prefix
2. Release type in Jira: always "Version"
3. Items inside the folder: "Patch {X.Y.Z.N} OpsComm CAE" for apps, "Release note {X.Y.Z.N} OpsComm CAE" for docs
4. When a new sub-patch arrives for an existing version, it is added to the existing portal folder (update the Jira ticket, not create a new one)

#### Current Portal Issues to Clean Up

The existing portal naming is inconsistent and should be migrated to the new convention over time:

- Inconsistent prefix: mix of "Version", "Patch", "Update" for folder names → standardize to "Version v{X.Y.Z}"
- Inconsistent "v" prefix: "v8.0.28" vs "7.3.26" vs "v7.3.25" → always use "v"
- Bundled names: "Version 8.1.[1,2,3,4,5,6,7,8,9,10]" → break into individual version folders
- Miscellaneous: "WS Upgrade v8", "PSA Upgrade 7.3", "Webdev28" → review and recategorize

---

## 7. Stage 5 — Future: Automated Jira Integration via Atlassian MCP

The planned Jira automation leverages the Atlassian Model Context Protocol (MCP) server, which enables direct programmatic integration with Jira Cloud. This approach was demonstrated by Pallav Gupta (Principal Software Architect, Operations Research Team) on October 8, 2025, showcasing automated story creation, JQL queries, and Confluence integration.

### Integration Architecture

The Atlassian MCP server connects development tools to Atlassian Cloud services. For this pipeline, it will be configured to automatically create Jira tasks whenever a version is approved, using standardized templates and field mappings.

### Atlassian Cloud Configuration (Confirmed 2026-04-03)

- Cloud ID: `f835cbb2-8518-4c5a-857c-49f14108d0a6` (caeglobal.atlassian.net)
- Project Key: `CFSSOCP` (CFS-ServiceOps-CommPortal, id=10008)
- Authentication: **Classic API token + Basic Auth** (email:token against site URL)
- Scoped API tokens do NOT work for this instance — use classic tokens only
- Integration options: VS Code + Atlassian MCP, or direct REST API via Python `requests`

### Automated Task Creation Template

Each approved version will generate a Jira task following this standardized format:

```
Goal: {ONE_SENTENCE_OBJECTIVE}
Scope:
  - {KEY_DELIVERABLE_1}
  - {KEY_DELIVERABLE_2}
Acceptance Criteria:
  - {SPECIFIC_MEASURABLE_OUTCOME_1}
  - {SPECIFIC_MEASURABLE_OUTCOME_2}
Story Points: {ESTIMATED_POINTS}
Notes:
  - Parent Epic: {EPIC_KEY}
  - Team: {TEAM_NAME}
  - Priority: {HIGH|MEDIUM|LOW}
```

### Story Point Estimation

- 1-2 points: Simple updates, documentation fixes
- 3 points: Basic setup, configuration, templates
- 5 points: Implementation, development, POCs
- 8 points: Complex integrations, pipelines
- 13 points: Major platform work (should be broken down)

### Key MCP Commands for Pipeline Integration

- `createJiraIssue` — Create tasks with comprehensive details and field mappings
- `editJiraIssue` — Update existing issue descriptions
- `searchJiraIssuesUsingJql` — Query and validate existing issues
- `getConfluencePage` — Retrieve and link documentation

### Confirmed Field Mappings

- Story Points: `customfield_10034`
- Team Assignment: `customfield_10001`
- Epic Link: `parent` field in API
- Assignee: `assignee_account_id`

### Prerequisites for Enabling Automation

1. Obtain Jira admin access for API token generation
2. Install and configure Atlassian MCP server
3. Map pipeline project to correct Jira project key
4. Configure task templates with correct field IDs
5. Test with a single version before enabling for all releases

---

## 8. Folder Structure & State Tracking

### Pipeline Folder Layout (Patch-Centric)

```
OpsCommDocsPipeline/
├── config/
│   ├── pipeline.json              # State tracker (full audit trail)
│   └── pipeline_flow.json         # Pipeline stage definitions & naming rules
├── patches/
│   ├── ACARS_V8_1/
│   │   ├── 8.1.11.0/             # Patch (independent deliverable)
│   │   │   ├── incoming/         # Full SFTP mirror (Binaries/, Script/, etc.)
│   │   │   └── approved/         # Reviewed, ready for Jira
│   │   └── 8.1.11.2/
│   │       ├── incoming/
│   │       └── approved/
│   ├── ACARS_V8_0/
│   │   └── ...
│   └── Flightscape_7_3/
│       ├── 7_3_27_0/
│       │   ├── incoming/
│       │   └── approved/
├── templates/
│   └── Flightscape-English-External Business Document.docx
```

### State Tracker (pipeline.json)

The state tracker records the full lifecycle of every patch passing through the pipeline. For each patch, it tracks:

- Patch status: in_progress, processed, approved, published
- Download: timestamp, file manifest (all folders and files)
- Processing: whether docs (if present) have been templated
- Approval: who approved, when, and any notes
- Jira tickets: ticket IDs, status, creation timestamp, URL (populated when integration is active)

---

## 9. Version & Patch Naming Conventions

### ACARS Naming (Hierarchical)

**Product folder → Version folder → Patch folder:**

Example: `ACARS_V8_1` → `ACARS_V8_1_11` → `8.1.11.0`

Each patch (e.g., 8.1.11.0, 8.1.11.2) is an independent deliverable.

### Flightscape Naming (Flat)

**Patch folder format:** `{major}_{minor}_{patch}_{sub}`

Example: `7_3_27_5` → Patch 5 of version 7.3.27

No parent version folder; each patch folder is independent. Known subfolders may vary (WEBAPPS, DOC, Scripts, Binaries, etc.).

### Patch Independence

Each patch (e.g., 7_3_27_0, 7_3_27_5, 8.1.11.0) is approved and published independently. There is no automatic bundling. Patches sharing the same major version may be grouped for release notes purposes, but the pipeline processes them as separate, trackable deliverables.

### Developer Portal Naming

On the customer-facing developer portal, patches are grouped by version folder (e.g., "Version v7.3.25" containing patches 7.3.25.0, 7.3.25.1, 7.3.25.2). Release notes and downloadable applications are linked to their specific sub-patches within each version folder.

---

## 10. Product Lines & SFTP Structure

The SFTP server hosts multiple product lines, each with different organizational structures. The pipeline must handle all of them:

### Focus Product Lines

- **ACARS V8.1:** Hierarchical structure (`ACARS_V8_1` → `ACARS_V8_1_11` → `8.1.11.0/`)
- **ACARS V8.0:** Hierarchical structure (`ACARS_V8_0` → version folder → patch folder/)
- **Flightscape 7.3:** Flat structure (`7_3_27_0/`, `7_3_27_5/`, etc.)

### Other Known Product Lines

- ACARS V7.x: Legacy versions with hierarchical structure
- ACARS V6.x: Legacy versions with hierarchical structure
- AIRPORT_SCRIPTS: Script delivery package
- B2B_LASTRELEASE: B2B integration releases
- BSN: Business support network

### Subfolder Variation

Different product lines use different subfolder names. Common variations include:

- Binary folders: Binaries, WEBAPPS (sometimes both in same patch)
- Script folders: Script, Scripts
- Documentation: DOC
- Service folders: Web Applications, Web Services

*The pipeline must preserve the full structure of each patch as-is and not assume a fixed subfolder layout.*

---

## 11. Atlassian MCP Integration Reference

This section provides detailed reference material from the Atlassian MCP demo conducted on October 8, 2025, by Pallav Gupta (pallav.gupta@cae.com), Principal Software Architect, Operations Research Team.

### What is Atlassian MCP?

The Atlassian Model Context Protocol (MCP) server enables direct integration between development tools and Atlassian Cloud services, allowing for automated interactions with Jira and Confluence through natural language commands.

### Setup Steps

1. MCP Server Installation: Install and configure the Atlassian MCP server
2. Authentication: Secure connection to Atlassian Cloud instance
3. VS Code Integration: Configure Copilot with custom instructions
4. Verification: Test basic connectivity and permissions

### JQL Query Examples

```sql
# List all issues assigned to current user
assignee = currentUser() ORDER BY created DESC

# Find stories in specific epic
project = FSOR AND "Epic Link" = FSOR-100

# Search by team assignment
project = FSOR AND team = "The Solver Syndicate" ORDER BY created DESC

# Status-based queries
project = FSOR AND status = "In Progress"
```

### Confluence Integration

- Content Search: Using CQL (Confluence Query Language) for advanced searches
- Page Creation: Automated page creation with structured templates
- Bidirectional Linking: Connect Jira issues to Confluence documentation
- Automated Documentation: Generate pages from project activities

### Batch Story Creation

The demo showed creating multiple stories from a text file (story_list.txt) in under 2 minutes. This capability can be leveraged to create pipeline Jira tasks in batch when multiple versions are approved simultaneously.

### Common Issues & Solutions

- Login Token Expiration: Restart MCP server when authentication fails
- Custom Field Mapping: Ensure correct field IDs in instructions
- Permission Verification: Validate project access and issue creation rights
- API Limitations: Include missing field data in descriptions as fallback

### Demonstrated Results

- Story Creation Speed: 90% faster than manual creation
- Description Quality: 100% template compliance
- Batch Processing: 8 stories created from single file input in under 2 minutes

---

## 12. Next Steps & Roadmap

### Completed

1. ~~Test SFTP connection and confirm exact folder structure for all product lines~~ ✓ (2026-04-03)
2. ~~Create the SFTP polling and sorting script~~ ✓ (`scripts/test_sftp.py`)
3. ~~Build the state tracker update logic~~ ✓ (per-product JSON trackers)
4. ~~Jira API connection tested and field mappings confirmed~~ ✓ (`scripts/test_jira.py`)
5. ~~Map pipeline fields to Jira project/field IDs~~ ✓ (all 10 required fields for issue type 10163)

### Immediate — Jira Automation (In Progress)

1. Create a real test ticket to confirm Jira accepts the payload
2. Test attachment upload (zip binaries + POST to ticket)
3. Build `create_jira_ticket.py` — takes patch ID, creates ticket, writes ticket key to state
4. Add new/existing folder detection (JQL query for existing version tickets)
5. Test with a single version before batch processing

### Short-Term — Binaries Pipeline End-to-End

1. Real SFTP download (currently simulated)
2. Approval workflow via API/UI
3. Jira ticket creation triggered by approval
4. Attachment upload (zip + attach approved binaries)
5. Status tracking (poll ticket status, update state)
6. Batch processing for multiple simultaneous approvals

### Medium-Term — Docs Pipeline & Infrastructure

1. Obtain example raw documentation files for converter development
2. Build the document template converter (docx-to-docx with CAE branding)
3. FastAPI backend + Next.js frontend + Docker Compose
4. Dashboard for pipeline monitoring and approval

### Future Enhancements

- PDF fallback: Add PDF-to-docx extraction for docs that arrive as PDFs
- Notifications: Alert the release manager when new versions appear on SFTP
- Confluence integration: Auto-generate release notes pages in Confluence
- Scheduled automation: Run the full pipeline on a cron schedule
