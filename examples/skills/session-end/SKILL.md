# /session-end

Run the end-of-session checklist, close the session in the dashboard, and verify everything is wrapped up.

## Important rules

> **Only close the session belonging to THIS conversation.**
> If there are multiple active sessions, the others belong to other Claude Code conversations.
> Never close, park, or mark other sessions as stale.

## Instructions

### Step 1: Check uncommitted changes

- Run `git status`
- Run `git diff --name-only` to see changed files

### Step 2: Check documentation updates

- Has CHANGELOG.md been updated?
- Has README.md been updated?
- Have other relevant docs been updated?

### Step 3: Run quality checks

- Run your project's lint/test/build commands

### Step 4: Close session in dashboard

1. **Find the active session** for this project:
   ```bash
   python3 ~/.claude/dashboard/manage.py active-sessions --project <slug>
   ```
   If multiple active sessions exist, ask which one belongs to THIS conversation.

2. **Ask via AskUserQuestion: "How do you want to close this session?"**
   - Option 1: **"Complete"** — session is done
   - Option 2: **"Park"** — session will be resumed later (with reason)

3. **On complete**, gather:
   - **Outcome:** short description of what was achieved
   - **Next 3 steps:** what needs to happen next?

   Register:
   ```bash
   python3 ~/.claude/dashboard/manage.py complete-session <session_id> \
     --outcome "<what was achieved>" \
     --next-steps "step 1" "step 2" "step 3" \
     --files-changed <changed files from git diff>
   ```

4. **On park**, gather:
   - **Reason:** why is the session being parked?
   - **Next 3 steps:** what needs to happen when the blocker is resolved?

   Register:
   ```bash
   python3 ~/.claude/dashboard/manage.py park-session <session_id> \
     --reason "<reason>" \
     --next-steps "step 1" "step 2" "step 3"
   ```

### Step 5: Show checklist

```
End-of-session checklist:
- [x/!] Uncommitted changes: <count> / none
- [x/!] CHANGELOG.md updated: yes / no
- [x/!] Quality checks: passed / failed
- [x/!] Session closed: yes (completed/parked) / no
```

Confirm with:
```
Session <session_id> closed: <completed/parked>
Outcome: <outcome or parked_reason>
Next steps:
  1. <step>
  2. <step>
  3. <step>
```
