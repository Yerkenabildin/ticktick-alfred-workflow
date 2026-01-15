# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Alfred Workflow for TickTick task management integration. Python 3 backend with vendored dependencies.

## Architecture

```
src/
├── api/           # TickTick API layer (task.py, list.py)
├── utils/         # Utilities: constants, displays, filters, parse, sync
├── *.py           # Entry point scripts triggered by Alfred keywords
└── [vendored]/    # requests, ualfred, parsedatetime, certifi, urllib3, idna, charset_normalizer
```

### Entry Points (Alfred Keywords)

- **Task operations:** `task-search.py` (tl), `task-new-helper.py`/`task-new-post.py` (tn), `task-complete.py` (Cmd+Enter)
- **List operations:** `list-search.py` (tls), `list-new-helper.py`/`list-new-post.py`
- **Setup:** `setup-access-token.py` (tsetup1/tsetup2), `setup-sync.py` (tsync)

### Key Patterns

- Alfred workflow config in `info.plist` (XML format)
- `ualfred` library handles Alfred JSON output and secure credential storage
- 5-minute cache with manual sync via `tsync`
- Natural language date parsing via `parsedatetime` ("tomorrow 5pm", "next week")

## Development

No build/test/lint system. Dependencies pre-vendored in `src/`.

### Testing Changes

1. Symlink or copy workflow to `~/Library/Application Support/Alfred/Alfred.alfredpreferences/workflows/`
2. Test via Alfred command bar using keywords: `tl`, `tn`, `tls`, `tsync`
3. Debug output visible in Alfred's debugger (Cmd+D in Alfred Preferences > Workflows)

### API Integration

- Base URL: `https://api.ticktick.com/open/v1`
- Auth: Bearer token from OAuth2 flow
- Endpoints in `src/utils/constants.py`

## Known Limitations

- Task search requires separate API call per list (slow with many lists)
- Cannot search Inbox tasks (API limitation)
- Can only add tasks to Inbox (API limitation)
