# /session-start

Start a new work session: loads project context, registers the session in the dashboard, and asks what you'll be working on.

## Important rules

> **NEVER close or modify existing active sessions.**
> Multiple active sessions is normal — each Claude Code window has its own session.
> This skill may **only** create a new session.

## Instructions

### Step 1: Register project & create session

1. **Register the project** (idempotent):
   ```bash
   python3 ~/.claude/dashboard/manage.py register-project \
     --name "<project name>" \
     --path "<absolute path to project root>"
   ```

2. **Get active and parked sessions** (parallel):
   ```bash
   python3 ~/.claude/dashboard/manage.py active-sessions --project <slug>
   python3 ~/.claude/dashboard/manage.py parked-sessions --project <slug>
   ```

3. **Create a session** with placeholder intent:
   ```bash
   python3 ~/.claude/dashboard/manage.py create-session \
     --project <slug> \
     --intent "Session starting up..." \
     --git-branch <current branch>
   ```
   Save the `session_id` from the output.

4. **Register the first event:**
   ```bash
   python3 ~/.claude/dashboard/manage.py add-event <session_id> --message "Session started"
   ```

### Step 2: Load project context (parallel)

Read your key project files (e.g., README, roadmap, changelog).

Update activity on the dashboard:
```bash
python3 ~/.claude/dashboard/manage.py update-session <session_id> --current-activity "Loading project files"
```

### Step 3: Git status

- `git status` — uncommitted changes
- `git log --oneline -10` — recent commits

### Step 4: Show summary

Display an overview with:
- Active and parked sessions
- Project status and current phase
- Next steps from roadmap
- Git status

### Step 5: Ask for intent & update session

1. **If parked sessions exist**, ask via AskUserQuestion:
   - Option 1: "Resume: {intent}" (with reason)
   - Option 2: "Start new session"
   - On resume:
     ```bash
     python3 ~/.claude/dashboard/manage.py resume-session <session_id>
     python3 ~/.claude/dashboard/manage.py complete-session <placeholder_session_id> --outcome "Replaced by resumed session"
     ```

2. **If no parked sessions** (or user picks "new"), ask what they'll work on.

3. **Update the session** with the real intent:
   ```bash
   python3 ~/.claude/dashboard/manage.py update-session <session_id> \
     --intent "<what the user will do>" \
     --roadmap-ref "<phase reference>"
   python3 ~/.claude/dashboard/manage.py add-event <session_id> --message "Intent set: <intent>"
   ```

### Step 6: Confirmation

```
Session registered: <session_id>
Intent: <intent>
Project: <name> | Phase: <current_phase>
```
