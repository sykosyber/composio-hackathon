# Composio tools used (verified live, 2026-10-19 12:40 PT)

Transport: Composio MCP `https://connect.composio.dev/mcp` with header `x-consumer-api-key: $COMPOSIO_API_KEY` (`ck_...`).
Each pipeline step calls `COMPOSIO_MULTI_EXECUTE_TOOL` with exactly one fixed slug and fixed arguments, so the
model never chooses tools. A project key (`ak_...`) switches `app/composio_actions.py` to the Python SDK
(`composio.tools.execute`). Connected accounts (all ACTIVE): gmail, googlesheets, slack.

| Step | Slug | Arguments we send | Result we keep |
|---|---|---|---|
| Sheet header / row update | `GOOGLESHEETS_VALUES_UPDATE` | `spreadsheet_id`, `range` (`Sheet1!A{row}`), `value_input_option=RAW`, `values` | ok |
| Sheet append | `GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND` | `spreadsheetId`, `range=Sheet1!A1`, `valueInputOption=RAW`, `insertDataOption=INSERT_ROWS`, `values` | `updates.updatedRange` -> row number |
| Gmail draft (never sent) | `GMAIL_CREATE_EMAIL_DRAFT` | `recipient_email` (AGENCY_DRAFT_TO), `subject` (`[PIN-<id>] ...`), `body`, `is_html=false` | draft `id` |
| Slack post | `SLACK_SEND_MESSAGE` | `channel` (C0CAABPUP1T = #all-neighborhood), `markdown_text` | `ts` |
| Agency reply watch | `GMAIL_FETCH_EMAILS` | `query="subject:PIN newer_than:2d -in:drafts -in:sent -from:me"`, `max_results=10`, `include_payload=true` | `messageId`, `subject`, `preview.body` |
| Setup only | `GOOGLESHEETS_GET_SHEET_NAMES`, `SLACK_LIST_ALL_CHANNELS` | | tab `Sheet1`; channel ids |

Not available with a consumer key: trigger APIs. Agency replies are detected by polling `GMAIL_FETCH_EMAILS` every
`GMAIL_POLL_S` (8s), which is also faster than Composio's Gmail trigger (polling, up to ~15 min latency).

Smoke test: `.venv/Scripts/python scripts/smoke_composio.py` -> PASS at 12:43 (Sheet append 0.96s, Gmail draft 1.8s,
Slack 0.8s, Sheet update 0.8s).
