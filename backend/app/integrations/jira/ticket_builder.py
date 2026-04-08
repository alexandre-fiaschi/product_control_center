"""Pure functions for building Jira ticket payloads from pipeline config."""

from typing import Any


def text_to_adf(text: str) -> dict[str, Any]:
    """Convert plain text to Atlassian Document Format, preserving line breaks."""
    content: list[dict] = []
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
        "content": [{"type": "paragraph", "content": content}],
    }


def _build_payload(
    patch_id: str,
    version: str,
    is_new_folder: bool,
    jira_config: dict[str, Any],
    ticket_type: str,
) -> dict[str, Any]:
    """Internal helper that builds payload for either binaries or docs ticket."""
    fields_cfg = jira_config["fields"]

    summary_template = jira_config["summary_templates"][ticket_type]
    summary = summary_template.format(patch_id=patch_id)

    release_name = fields_cfg["release_name"]["template"].format(version=version)
    new_or_existing = "new" if is_new_folder else "existing"

    description_text = jira_config["description_template"].format(
        version=version,
        new_or_existing=new_or_existing,
        release_name=release_name,
    )

    cur_key = "new" if is_new_folder else "existing"
    create_update_value = fields_cfg["create_update_remove"]["values"][cur_key]

    return {
        "fields": {
            "project": {"key": jira_config["project_key"]},
            "issuetype": {"id": jira_config["issue_type_id"]},
            "summary": summary,
            "description": text_to_adf(description_text),
            fields_cfg["client"]["id"]: fields_cfg["client"]["value"],
            fields_cfg["environment"]["id"]: fields_cfg["environment"]["value"],
            fields_cfg["product_name"]["id"]: fields_cfg["product_name"]["value"],
            fields_cfg["release_name"]["id"]: release_name,
            fields_cfg["release_type"]["id"]: fields_cfg["release_type"]["value"],
            fields_cfg["release_approval"]["id"]: fields_cfg["release_approval"]["value"],
            fields_cfg["create_update_remove"]["id"]: create_update_value,
        }
    }


def build_binaries_payload(
    patch_id: str, version: str, is_new_folder: bool, jira_config: dict[str, Any]
) -> dict[str, Any]:
    """Build complete Jira issue payload for a binaries ticket."""
    return _build_payload(patch_id, version, is_new_folder, jira_config, "binaries")


def build_docs_payload(
    patch_id: str, version: str, is_new_folder: bool, jira_config: dict[str, Any]
) -> dict[str, Any]:
    """Build complete Jira issue payload for a docs ticket."""
    return _build_payload(patch_id, version, is_new_folder, jira_config, "docs")
