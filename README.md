# Claude Sessions Dashboard

A lightweight, file-based session tracker and web dashboard for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Track what you're working on across multiple projects and sessions — with a real-time web UI.

## What it does

When you use Claude Code across multiple projects and terminal windows, it's easy to lose track of what you were doing. This dashboard gives you:

- **Session tracking** — each Claude Code conversation registers as a session with an intent, events, and outcome
- **Task tracking** — sessions can have tasks with status (pending/in_progress/completed/skipped), shown as a progress bar in the UI
- **Park & resume** — pause a session with a reason and pick it up later
- **Stale detection** — sessions without a heartbeat for 24h are flagged
- **Auto-cleanup** — stale sessions are automatically closed via a CLI command or launchd periodic job
- **Concurrency safe** — all session mutations are protected by file-level locking (`fcntl.flock`)
- **Project overview** — see all your projects, their current phase, and roadmap progress
- **Export** — export sessions or entire projects as JSON or Markdown, via CLI, API, or download buttons in the dashboard
- **Web dashboard** — dark-themed, auto-refreshing UI at `localhost:9000`
- **Zero dependencies** — the core runs on Python stdlib only (web UI needs `fastapi` + `uvicorn`)

## Screenshot

```
┌─────────────────────────────────────────────────────┐
│ Claude Sessions                      Updated: 10:32 │
├─────────────────────────────────────────────────────┤
│ [All (5)] [Active (1)] [Parked (1)] [Completed (3)] │
│                                                     │
│ ▸ My Project                    Phase: v2.0         │
│   Sessions: 5  Active: 1  Parked: 1                │
│                                                     │
│ ▸ ● Fix auth bug          Writing tests   2m ago   │
│ ▸ ● Add dark mode         (parked)       1h ago    │
│ ▸ ○ Refactor API          Done           3h ago    │
└─────────────────────────────────────────────────────┘
```

## Installation

### 1. Copy the dashboard files

```bash
# Clone this repo
git clone https://github.com/RobinEste/claude-sessions-dashboard.git

# Copy to Claude Code's config directory
cp -r claude-sessions-dashboard/* ~/.claude/dashboard/

# Make scripts executable
chmod +x ~/.claude/dashboard/manage.py
chmod +x ~/.claude/dashboard/heartbeat.sh
```

### 2. Install web dashboard dependency (optional)

The CLI works without any dependencies. For the web dashboard:

```bash
pip install fastapi uvicorn
```

### 3. Configure the heartbeat hook (optional)

Add to your `~/.claude/settings.json` to keep sessions alive automatically:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/dashboard/heartbeat.sh",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

This runs after every Claude Code turn and updates the heartbeat for active sessions (throttled to once per 15 minutes).

### 4. Auto-start on login (macOS, optional)

To keep the web dashboard running automatically:

```bash
# Create logs directory
mkdir -p ~/.claude/dashboard/logs

# Copy the example plist and edit it
cp examples/launchd/com.claude.sessions-dashboard.plist ~/Library/LaunchAgents/

# Edit the plist: replace YOUR_USERNAME and set the correct python3 path
# Find your python3 path with: which python3
nano ~/Library/LaunchAgents/com.claude.sessions-dashboard.plist

# Load the agent
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.claude.sessions-dashboard.plist
```

The dashboard will now:
- Start automatically when you log in
- Restart if it crashes (`KeepAlive`)
- Log to `~/.claude/dashboard/logs/`

To stop: `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.claude.sessions-dashboard.plist`

### 5. Auto-cleanup stale sessions (macOS, optional)

Automatically close sessions that have been inactive for 24+ hours:

```bash
# Copy the cleanup plist
cp examples/launchd/com.claude.sessions-cleanup.plist ~/Library/LaunchAgents/

# Edit: replace YOUR_USERNAME and python3 path
nano ~/Library/LaunchAgents/com.claude.sessions-cleanup.plist

# Load
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.claude.sessions-cleanup.plist
```

This runs `manage.py cleanup-stale` every hour. You can also run it manually:

```bash
python3 ~/.claude/dashboard/manage.py cleanup-stale
```

## Usage

### CLI

All commands output JSON, making them easy to use in Claude Code skills and scripts.

```bash
# Register a project
python3 ~/.claude/dashboard/manage.py register-project \
  --name "My Project" --path "/path/to/project"

# Create a session
python3 ~/.claude/dashboard/manage.py create-session \
  --project my-project --intent "Fix the login bug" --git-branch main

# Add events as you work
python3 ~/.claude/dashboard/manage.py add-event <session_id> \
  --message "Found root cause in auth middleware"

# Update what you're doing
python3 ~/.claude/dashboard/manage.py update-session <session_id> \
  --current-activity "Writing tests"

# Park a session (come back later)
python3 ~/.claude/dashboard/manage.py park-session <session_id> \
  --reason "Blocked on API access" \
  --next-steps "Get API key" "Implement auth flow" "Write tests"

# Resume a parked session
python3 ~/.claude/dashboard/manage.py resume-session <session_id>

# Complete a session
python3 ~/.claude/dashboard/manage.py complete-session <session_id> \
  --outcome "Login bug fixed, 3 tests added" \
  --next-steps "Deploy to staging" "Monitor error rates"

# Track tasks within a session
python3 ~/.claude/dashboard/manage.py add-tasks <session_id> \
  --subjects "Fix login bug" "Add tests" "Update docs"

# Update a task's status
python3 ~/.claude/dashboard/manage.py update-task <session_id> <task_id> \
  --status completed

# List sessions
python3 ~/.claude/dashboard/manage.py active-sessions --project my-project
python3 ~/.claude/dashboard/manage.py parked-sessions
python3 ~/.claude/dashboard/manage.py stale-sessions

# Clean up stale sessions (inactive for 24+ hours)
python3 ~/.claude/dashboard/manage.py cleanup-stale

# Track roadmap progress
python3 ~/.claude/dashboard/manage.py update-project-state my-project \
  --current-phase "v2.0 Beta" \
  --completed "Auth system" "API v2" \
  --in-progress "Dashboard UI" \
  --next-up "Testing" "Documentation" "Deploy"

# Export a session as Markdown
python3 ~/.claude/dashboard/manage.py export <session_id> --format markdown

# Export all sessions for a project as JSON
python3 ~/.claude/dashboard/manage.py export <project_slug> --format json

# Export to file
python3 ~/.claude/dashboard/manage.py export <session_id> --format markdown -o session.md

# Full overview (used by web dashboard)
python3 ~/.claude/dashboard/manage.py overview
```

### Web dashboard

```bash
python3 ~/.claude/dashboard/manage.py serve
# → Dashboard: http://127.0.0.1:9000
```

The web dashboard polls `/api/overview` every 30 seconds and shows all sessions grouped by project.

### Claude Code skills (recommended)

The real power comes from integrating the dashboard with Claude Code skills. See the `examples/skills/` folder for ready-to-use `/session-start` and `/session-end` skills.

Copy them to your project:

```bash
cp -r examples/skills/session-start .claude/skills/
cp -r examples/skills/session-end .claude/skills/
```

Then use `/session-start` at the beginning and `/session-end` at the end of each Claude Code conversation.

## Architecture

```
~/.claude/dashboard/
├── manage.py          # CLI entry point (all commands)
├── heartbeat.sh       # Throttled heartbeat (Claude Code hook)
├── config.json        # Project registry + settings (auto-created)
├── lib/
│   ├── models.py      # Dataclasses (Session, ProjectState, etc.)
│   ├── store.py       # JSON file CRUD with atomic writes + file locking
│   └── export.py      # Export formatting (JSON + Markdown, no I/O)
├── web/
│   ├── app.py         # FastAPI server (5 routes)
│   └── index.html     # Dashboard frontend (single HTML file)
├── sessions/          # Session JSON files (auto-created)
└── projects/          # Project state JSON files (auto-created)
```

### Design decisions

- **File-based storage** — no database needed; each session is a JSON file. Atomic writes (`tempfile` + `os.replace`) prevent corruption from concurrent access.
- **File-level locking** — all session mutations are protected by exclusive locks (`fcntl.flock`) on dedicated `.lock` files. This prevents race conditions when multiple Claude Code windows modify sessions concurrently.
- **Zero core dependencies** — the CLI and data layer use only Python stdlib (`json`, `dataclasses`, `pathlib`, `fcntl`). Only the web dashboard needs `fastapi`/`uvicorn`.
- **Throttled heartbeat** — the shell hook uses file modification timestamps to skip unnecessary Python invocations (< 5ms when throttled).
- **Multi-session safe** — multiple Claude Code windows can run simultaneously. Each manages its own session; skills never touch sessions from other conversations.

## Data stored

Sessions track:
- **Intent** — what you planned to do
- **Current activity** — what you're doing right now
- **Tasks** — subtasks with status (pending/in_progress/completed/skipped) and progress bar
- **Events** — timestamped log of significant actions
- **Commits** — git commits made during the session
- **Files changed** — which files were modified
- **Decisions** — significant choices made during the session
- **Next steps** — what needs to happen after this session
- **Roadmap ref** — which project phase this session relates to

All data is stored locally in `~/.claude/dashboard/` and never leaves your machine.

## Requirements

- Python 3.11+ (uses `StrEnum`, `X | Y` union syntax)
- FastAPI + Uvicorn (only for the web dashboard)
- Claude Code (for hook integration)

## License

MIT
