# OpsComm Pipeline — Frontend Reference

This document is a reference for the frontend developer. It covers every view, the API endpoint it calls, the JSON response shape, and UI mockups showing how to render the data.

---

## API Endpoints Summary

| Method | Endpoint | View |
|--------|----------|------|
| POST | `/api/pipeline/scan` | Scan button (all products) |
| POST | `/api/pipeline/scan/{product_id}` | Scan button (single product) |
| GET | `/api/products` | Dashboard — product list |
| GET | `/api/products/{product_id}` | Product detail page |
| GET | `/api/patches` | Global patch list (all products) |
| GET | `/api/patches/{product_id}` | Patch list for a product |
| GET | `/api/patches/{product_id}/{patch_id}` | Patch detail — full timeline |
| POST | `/api/patches/{product_id}/{patch_id}/binaries/approve` | Approve binaries button |
| POST | `/api/patches/{product_id}/{patch_id}/docs/approve` | Approve docs button |
| GET | `/api/dashboard/summary` | Dashboard — summary counts |

---

## 1. Dashboard

**Endpoint:** `GET /api/dashboard/summary`

### Response

```json
{
  "total_patches": 35,
  "binaries": {
    "pending_approval": 5,
    "approved": 0,
    "published": 30
  },
  "release_notes": {
    "not_started": 3,
    "pending_approval": 7,
    "published": 25
  },
  "by_product": [
    {
      "product_id": "ACARS_V8_1",
      "display_name": "ACARS V8.1",
      "actionable": 5,
      "published": 18,
      "total": 23
    },
    {
      "product_id": "ACARS_V8_0",
      "display_name": "ACARS V8.0",
      "actionable": 1,
      "published": 4,
      "total": 5
    },
    {
      "product_id": "ACARS_V7_3",
      "display_name": "ACARS V7.3",
      "actionable": 0,
      "published": 5,
      "total": 5
    }
  ],
  "last_scan": "2026-04-07T10:00:00Z"
}
```

### UI mockup

```
┌─────────────────────────────────────────────────────────────────┐
│  OpsComm Pipeline Dashboard                    [ Scan SFTP ]    │
│                                                                 │
│  Last scan: Apr 7, 10:00                                        │
│  Total patches: 35   Actionable: 6   Published: 29              │
│                                                                 │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐   │
│  │ ACARS V8.1      │ │ ACARS V8.0      │ │ ACARS V7.3      │   │
│  │                 │ │                 │ │                 │   │
│  │ 23 patches      │ │ 5 patches       │ │ 5 patches       │   │
│  │ 5 actionable    │ │ 1 actionable    │ │ 0 actionable    │   │
│  │ 18 published    │ │ 4 published     │ │ 5 published     │   │
│  │                 │ │                 │ │                 │   │
│  │ [ View ]        │ │ [ View ]        │ │ [ View ]        │   │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Product List

**Endpoint:** `GET /api/products`

### Response

```json
[
  {
    "product_id": "ACARS_V8_1",
    "display_name": "ACARS V8.1",
    "last_scanned_at": "2026-04-07T10:00:00Z",
    "counts": {
      "binaries": {
        "pending_approval": 5,
        "published": 18
      },
      "release_notes": {
        "not_started": 3,
        "pending_approval": 5,
        "published": 15
      }
    },
    "total_patches": 23
  }
]
```

---

## 3. Product Detail

**Endpoint:** `GET /api/products/{product_id}`

### Response

```json
{
  "product_id": "ACARS_V8_1",
  "display_name": "ACARS V8.1",
  "last_scanned_at": "2026-04-07T10:00:00Z",
  "versions": {
    "8.1.12": { "patch_count": 3 },
    "8.1.11": { "patch_count": 2 },
    "8.1.10": { "patch_count": 2 }
  },
  "counts": {
    "binaries": { "pending_approval": 5, "published": 18 },
    "release_notes": { "not_started": 3, "pending_approval": 5, "published": 15 }
  }
}
```

---

## 4. Patch List by Product

**Endpoint:** `GET /api/patches/{product_id}`

This is the **main working view**. It splits patches into two sections: actionable (needs attention) and history (done).

### Response

```json
{
  "product_id": "ACARS_V8_1",
  "actionable": [
    {
      "patch_id": "8.1.12.2",
      "version": "8.1.12",
      "binaries": {
        "status": "pending_approval",
        "jira_ticket_key": null,
        "jira_ticket_url": null
      },
      "release_notes": {
        "status": "pending_approval",
        "jira_ticket_key": null,
        "jira_ticket_url": null
      }
    },
    {
      "patch_id": "8.1.12.0",
      "version": "8.1.12",
      "binaries": {
        "status": "pending_approval",
        "jira_ticket_key": null,
        "jira_ticket_url": null
      },
      "release_notes": {
        "status": "not_started",
        "jira_ticket_key": null,
        "jira_ticket_url": null
      }
    }
  ],
  "history": [
    {
      "patch_id": "8.1.11.2",
      "version": "8.1.11",
      "binaries": {
        "status": "published",
        "jira_ticket_key": "CFSSOCP-1230",
        "jira_ticket_url": "https://caeglobal.atlassian.net/browse/CFSSOCP-1230",
        "published_at": "2026-04-05T14:22:00Z"
      },
      "release_notes": {
        "status": "published",
        "jira_ticket_key": "CFSSOCP-1231",
        "jira_ticket_url": "https://caeglobal.atlassian.net/browse/CFSSOCP-1231",
        "published_at": "2026-04-06T09:15:00Z"
      }
    }
  ]
}
```

### Actionable vs History rule

- **Actionable:** either `binaries.status != "published"` OR `release_notes.status != "published"`
- **History:** both are `"published"` — collapsed by default

### UI mockup

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ACARS V8.1                                                    [ Scan SFTP ]   │
│                                                                                 │
│  Actionable (5)                                                                 │
│  ┌───────────┬──────────────────────────────────┬──────────────────────────────┐ │
│  │ Patch     │ Binaries                         │ Release Notes               │ │
│  ├───────────┼──────────────────────────────────┼──────────────────────────────┤ │
│  │ 8.1.12.2  │ pending_approval  [ Approve ]    │ pending_approval [ Approve ]│ │
│  │ 8.1.12.1  │ pending_approval  [ Approve ]    │ pending_approval [ Approve ]│ │
│  │ 8.1.12.0  │ pending_approval  [ Approve ]    │ not_started                 │ │
│  │ 8.1.10.1  │ pending_approval  [ Approve ]    │ pending_approval [ Approve ]│ │
│  │ 8.1.10.0  │ pending_approval  [ Approve ]    │ pending_approval [ Approve ]│ │
│  └───────────┴──────────────────────────────────┴──────────────────────────────┘ │
│                                                                                 │
│  > History (18)  (click to expand)                                              │
│  ┌───────────┬──────────────────────────────────┬──────────────────────────────┐ │
│  │ Patch     │ Binaries                         │ Release Notes               │ │
│  ├───────────┼──────────────────────────────────┼──────────────────────────────┤ │
│  │ 8.1.11.2  │ published  CFSSOCP-1230  Apr 5  │ published  CFSSOCP-1231 Apr6│ │
│  │ 8.1.11.0  │ published  CFSSOCP-1228  Apr 3  │ published  CFSSOCP-1229 Apr4│ │
│  │ ...       │                                  │                             │ │
│  └───────────┴──────────────────────────────────┴──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Status rendering rules

| Status | Display | Button |
|--------|---------|--------|
| `not_started` | Grey badge | None |
| `pending_approval` | Yellow badge | `[ Approve ]` |
| `approved` | Blue badge | `[ Retry ]` (means Jira failed) |
| `pdf_exported` | Blue badge | `[ Retry ]` (means Jira failed) |
| `published` | Green badge + Jira link + date | None |

### Jira links in history

Every `jira_ticket_key` is a clickable link using `jira_ticket_url`. Display as: `CFSSOCP-1234` linking to `https://caeglobal.atlassian.net/browse/CFSSOCP-1234`.

---

## 5. Patch Detail — Full Timeline

**Endpoint:** `GET /api/patches/{product_id}/{patch_id}`

### Response

```json
{
  "product_id": "ACARS_V8_1",
  "patch_id": "8.1.12.2",
  "version": "8.1.12",
  "sftp_folder": "8.1.12.2",
  "sftp_path": "/ACARS_V8_1/ACARS_V8_1_12/8.1.12.2",
  "binaries": {
    "status": "published",
    "discovered_at": "2026-04-07T10:00:00Z",
    "downloaded_at": "2026-04-07T10:00:05Z",
    "approved_at": "2026-04-07T14:22:00Z",
    "published_at": "2026-04-07T14:22:03Z",
    "jira_ticket_key": "CFSSOCP-1234",
    "jira_ticket_url": "https://caeglobal.atlassian.net/browse/CFSSOCP-1234",
    "files": ["installer.exe", "config.xml", "readme.txt"]
  },
  "release_notes": {
    "status": "published",
    "discovered_at": "2026-04-07T10:00:00Z",
    "downloaded_at": "2026-04-07T10:00:05Z",
    "converted_at": "2026-04-07T10:00:06Z",
    "approved_at": "2026-04-08T09:15:00Z",
    "pdf_exported_at": "2026-04-08T09:15:01Z",
    "published_at": "2026-04-08T09:15:04Z",
    "jira_ticket_key": "CFSSOCP-1235",
    "jira_ticket_url": "https://caeglobal.atlassian.net/browse/CFSSOCP-1235",
    "docx_path": "patches/ACARS_V8_1/8.1.12.2/release_notes.docx",
    "pdf_path": "patches/ACARS_V8_1/8.1.12.2/release_notes.pdf"
  }
}
```

### UI mockup — fully published patch

```
┌─────────────────────────────────────────────────────┐
│  Patch 8.1.12.2                      ACARS V8.1     │
│                                                     │
│  Binaries                  CFSSOCP-1234             │
│  ├── Discovered      Apr 7, 10:00                   │
│  ├── Downloaded      Apr 7, 10:00                   │
│  ├── Approved        Apr 7, 14:22                   │
│  └── Published       Apr 7, 14:22                   │
│                                                     │
│  Release Notes             CFSSOCP-1235             │
│  ├── Discovered      Apr 7, 10:00                   │
│  ├── Downloaded      Apr 7, 10:00                   │
│  ├── Converted       Apr 7, 10:00                   │
│  ├── Approved        Apr 8, 09:15                   │
│  ├── PDF Exported    Apr 8, 09:15                   │
│  └── Published       Apr 8, 09:15                   │
└─────────────────────────────────────────────────────┘
```

### UI mockup — patch still in progress

```
┌─────────────────────────────────────────────────────┐
│  Patch 8.1.12.2                      ACARS V8.1     │
│                                                     │
│  Binaries                                           │
│  ├── Discovered      Apr 7, 10:00                   │
│  ├── Downloaded      Apr 7, 10:00                   │
│  └── Pending Approval                               │
│                              [ Approve ]             │
│                                                     │
│  Release Notes                                      │
│  ├── Discovered      Apr 7, 10:00                   │
│  ├── Downloaded      Apr 7, 10:00                   │
│  ├── Converted       Apr 7, 10:00                   │
│  └── Pending Approval                               │
│       Preview: [ Open .docx ]                        │
│                              [ Approve ]             │
└─────────────────────────────────────────────────────┘
```

### Timeline rendering rules

- Show each step with its timestamp
- Steps not yet reached: don't show them (timeline grows as patch progresses)
- If status is `pending_approval`: show `[ Approve ]` button at the end
- For docs at `pending_approval`: also show `[ Open .docx ]` download link
- Jira ticket key appears next to pipeline name only when `published`

---

## 6. Scan Button

**Endpoint:** `POST /api/pipeline/scan` (all) or `POST /api/pipeline/scan/{product_id}` (single)

### Response

```json
{
  "scanned_at": "2026-04-07T10:00:00Z",
  "products_scanned": ["ACARS_V8_1", "ACARS_V8_0", "ACARS_V7_3"],
  "new_patches": [
    {
      "product_id": "ACARS_V8_1",
      "patch_id": "8.1.12.2",
      "binaries_status": "pending_approval",
      "release_notes_status": "pending_approval"
    },
    {
      "product_id": "ACARS_V8_1",
      "patch_id": "8.1.12.3",
      "binaries_status": "pending_approval",
      "release_notes_status": "not_started"
    }
  ],
  "total_new": 2
}
```

### Frontend behavior

- Button shows loading spinner while scanning
- On success with new patches: toast "Scan complete — 2 new patches found", refresh patch list
- On success with 0 new: toast "No new patches found"
- On error: toast with error message

---

## 7. Approve Binaries

**Endpoint:** `POST /api/patches/{product_id}/{patch_id}/binaries/approve`

### Response (success)

```json
{
  "patch_id": "8.1.12.2",
  "pipeline": "binaries",
  "status": "published",
  "jira_ticket_key": "CFSSOCP-1234",
  "jira_ticket_url": "https://caeglobal.atlassian.net/browse/CFSSOCP-1234"
}
```

### Response (error)

```json
{
  "patch_id": "8.1.12.2",
  "pipeline": "binaries",
  "status": "approved",
  "error": "Jira ticket creation failed: 401 Unauthorized",
  "note": "Binaries approved but not published. Retry will attempt Jira again."
}
```

### Frontend behavior

- Button shows loading spinner while processing
- Success: toast with clickable Jira link, row updates to `published` with Jira key + date
- Error: toast with error message, `[ Approve ]` button changes to `[ Retry ]`

### Toast mockup (success)

```
┌──────────────────────────────────────────────┐
│  Binaries published                          │
│  Patch 8.1.12.2                              │
│  Jira: CFSSOCP-1234  (clickable link)        │
└──────────────────────────────────────────────┘
```

---

## 8. Approve Docs

**Endpoint:** `POST /api/patches/{product_id}/{patch_id}/docs/approve`

### Response (success)

```json
{
  "patch_id": "8.1.12.2",
  "pipeline": "docs",
  "status": "published",
  "jira_ticket_key": "CFSSOCP-1235",
  "jira_ticket_url": "https://caeglobal.atlassian.net/browse/CFSSOCP-1235"
}
```

### Response (error)

```json
{
  "patch_id": "8.1.12.2",
  "pipeline": "docs",
  "status": "approved",
  "error": "PDF export failed: unsupported font in template",
  "note": "Docs approved but PDF not generated. Fix template and retry."
}
```

### Frontend behavior

Same as binaries approve — toast with Jira link on success, error toast + Retry button on failure.

---

## 9. Global Patch List

**Endpoint:** `GET /api/patches`

**Optional query params:** `?status=pending_approval` or `?pipeline=docs&status=not_started`

### Response

Same shape as `GET /api/patches/{product_id}` but includes `product_id` on each patch and spans all products:

```json
{
  "actionable": [
    {
      "product_id": "ACARS_V8_1",
      "patch_id": "8.1.12.2",
      "version": "8.1.12",
      "binaries": { "status": "pending_approval", "jira_ticket_key": null, "jira_ticket_url": null },
      "release_notes": { "status": "pending_approval", "jira_ticket_key": null, "jira_ticket_url": null }
    },
    {
      "product_id": "ACARS_V8_0",
      "patch_id": "8.0.30.1",
      "version": "8.0.30",
      "binaries": { "status": "pending_approval", "jira_ticket_key": null, "jira_ticket_url": null },
      "release_notes": { "status": "not_started", "jira_ticket_key": null, "jira_ticket_url": null }
    }
  ],
  "history": [
    {
      "product_id": "ACARS_V8_1",
      "patch_id": "8.1.11.2",
      "version": "8.1.11",
      "binaries": {
        "status": "published",
        "jira_ticket_key": "CFSSOCP-1230",
        "jira_ticket_url": "https://caeglobal.atlassian.net/browse/CFSSOCP-1230",
        "published_at": "2026-04-05T14:22:00Z"
      },
      "release_notes": {
        "status": "published",
        "jira_ticket_key": "CFSSOCP-1231",
        "jira_ticket_url": "https://caeglobal.atlassian.net/browse/CFSSOCP-1231",
        "published_at": "2026-04-06T09:15:00Z"
      }
    }
  ]
}
```

### UI mockup

Same table as the per-product view, but with an extra "Product" column:

```
┌───────────┬───────────┬──────────────────────────────────┬──────────────────────────────┐
│ Product   │ Patch     │ Binaries                         │ Release Notes               │
├───────────┼───────────┼──────────────────────────────────┼──────────────────────────────┤
│ V8.1      │ 8.1.12.2  │ pending_approval  [ Approve ]    │ pending_approval [ Approve ]│
│ V8.1      │ 8.1.12.1  │ pending_approval  [ Approve ]    │ pending_approval [ Approve ]│
│ V8.0      │ 8.0.30.1  │ pending_approval  [ Approve ]    │ not_started                 │
└───────────┴───────────┴──────────────────────────────────┴──────────────────────────────┘
```

---

## Complete Pipeline Diagram

```
                              ┌─────────────────┐
                              │   SFTP Server    │
                              └────────┬─────────┘
                                       │
                              ┌────────▼─────────┐
                              │    SFTP SCAN      │  ◄── POST /api/pipeline/scan
                              │                   │
                              │ Discover + Download│
                              │ + Convert docs    │
                              └────────┬──────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    │                                      │
          ┌─────────▼──────────┐              ┌────────────▼───────────┐
          │     BINARIES       │              │    RELEASE NOTES       │
          │                    │              │                        │
          │  discovered        │              │  not_started           │
          │  downloaded        │              │  discovered            │
          │  pending_approval  │              │  downloaded            │
          │       │            │              │  converted             │
          │  [ Approve ]       │              │  pending_approval      │
          │       │            │              │       │                │
          │  approved          │              │  [ Approve ]           │
          │  zip + Jira        │              │       │                │
          │  published         │              │  approved              │
          │                    │              │  export PDF            │
          └─────────┬──────────┘              │  pdf_exported          │
                    │                         │  Jira + attach PDF     │
                    │                         │  published             │
                    │                         └────────────┬───────────┘
                    │                                      │
          ┌─────────▼──────────┐              ┌────────────▼───────────┐
          │  JIRA TICKET #1    │              │  JIRA TICKET #2        │
          │ "Add Release       │              │ "Add Release notes     │
          │  Version X.Y.Z.W"  │              │  X.Y.Z.W"             │
          │ Attach: .zip       │              │ Attach: .pdf           │
          └─────────┬──────────┘              └────────────┬───────────┘
                    │                                      │
                    └──────────────┬───────────────────────┘
                                   │
                          ┌────────▼──────────┐
                          │  CAE COMMUNITY    │
                          │  PORTAL           │
                          │                   │
                          │  Version X.Y.Z/   │
                          │   ├── X.Y.Z.W.zip │
                          │   └── X.Y.Z.W.pdf │
                          └───────────────────┘
```
