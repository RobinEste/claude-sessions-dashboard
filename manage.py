#!/usr/bin/env python3
"""CLI entry point for dashboard data operations.

Usage:
    python ~/.claude/dashboard/manage.py <command> [options]

All output is JSON — easy to parse by slash commands and web dashboard.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

# Add parent dir to path so `from lib import ...` works
sys.path.insert(0, str(Path(__file__).parent))

from lib import store
from lib.models import SessionStatus


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard session manager")
    sub = parser.add_subparsers(dest="command")

    # --- Project commands ---
    p = sub.add_parser("register-project", help="Register a project")
    p.add_argument("--name", required=True)
    p.add_argument("--path", required=True)

    sub.add_parser("list-projects", help="List registered projects")

    # --- Session commands ---
    p = sub.add_parser("create-session", help="Create a new active session")
    p.add_argument("--project", required=True, help="Project slug")
    p.add_argument("--intent", required=True, help="What this session will do")
    p.add_argument("--roadmap-ref", help="Roadmap reference (e.g. 'FASE D.3')")
    p.add_argument("--git-branch", default="main")

    p = sub.add_parser("get-session", help="Get session details")
    p.add_argument("session_id")

    p = sub.add_parser("heartbeat", help="Update session heartbeat")
    p.add_argument("session_id")

    p = sub.add_parser("complete-session", help="Mark session as completed")
    p.add_argument("session_id")
    p.add_argument("--outcome", required=True)
    p.add_argument("--next-steps", nargs="*", default=[])
    p.add_argument("--commits", help="JSON array of commit objects")
    p.add_argument("--files-changed", nargs="*", default=[])

    p = sub.add_parser("park-session", help="Park a session with reason")
    p.add_argument("session_id")
    p.add_argument("--reason", required=True)
    p.add_argument("--next-steps", nargs="*", default=[])

    p = sub.add_parser("resume-session", help="Resume a parked session")
    p.add_argument("session_id")
    p.add_argument("--intent", help="New intent (default: same as parked)")

    p = sub.add_parser("update-session", help="Update session fields")
    p.add_argument("session_id")
    p.add_argument("--intent", help="Update session intent")
    p.add_argument("--current-activity", help="What the session is doing now")
    p.add_argument("--roadmap-ref", help="Roadmap reference")

    p = sub.add_parser("add-event", help="Append event to session log")
    p.add_argument("session_id")
    p.add_argument("--message", required=True, help="Event message")

    p = sub.add_parser("heartbeat-project", help="Heartbeat all active sessions for a project")
    p.add_argument("project_slug")

    # --- Session queries ---
    p = sub.add_parser("active-sessions", help="List active sessions")
    p.add_argument("--project", help="Filter by project slug")

    p = sub.add_parser("parked-sessions", help="List parked sessions")
    p.add_argument("--project", help="Filter by project slug")

    sub.add_parser("stale-sessions", help="List stale sessions")

    p = sub.add_parser("list-sessions", help="List all sessions")
    p.add_argument("--project", help="Filter by project slug")
    p.add_argument("--status", choices=["active", "completed", "parked"])
    p.add_argument("--limit", type=int, default=20)

    # --- Project state ---
    p = sub.add_parser("project-state", help="Get project state")
    p.add_argument("project_slug")

    p = sub.add_parser("update-project-state", help="Update project roadmap info")
    p.add_argument("project_slug")
    p.add_argument("--current-phase")
    p.add_argument("--completed", nargs="*", help="Completed roadmap items")
    p.add_argument("--in-progress", nargs="*", help="In-progress roadmap items")
    p.add_argument("--next-up", nargs="*", help="Next 3 roadmap items")

    # --- Dashboard overview ---
    sub.add_parser("overview", help="Full dashboard overview")

    # --- Web server ---
    p = sub.add_parser("serve", help="Start web dashboard server")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--host", default="127.0.0.1")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    result = _dispatch(args)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _dispatch(args: argparse.Namespace) -> dict | list:
    cmd = args.command

    if cmd == "register-project":
        slug = store.register_project(args.name, args.path)
        return {"slug": slug, "status": "registered"}

    if cmd == "list-projects":
        projects = store.get_registered_projects()
        return {slug: asdict(p) for slug, p in projects.items()}

    if cmd == "create-session":
        session = store.create_session(
            project_slug=args.project,
            intent=args.intent,
            roadmap_ref=args.roadmap_ref,
            git_branch=args.git_branch,
        )
        return asdict(session)

    if cmd == "get-session":
        session = store.get_session(args.session_id)
        return asdict(session) if session else {"error": "Session not found"}

    if cmd == "update-session":
        kwargs = {}
        if args.intent is not None:
            kwargs["intent"] = args.intent
        if args.current_activity is not None:
            kwargs["current_activity"] = args.current_activity
        if args.roadmap_ref is not None:
            kwargs["roadmap_ref"] = args.roadmap_ref
        session = store.update_session(args.session_id, **kwargs)
        return asdict(session) if session else {"error": "Session not found"}

    if cmd == "add-event":
        session = store.add_event(args.session_id, args.message)
        return asdict(session) if session else {"error": "Session not found"}

    if cmd == "heartbeat":
        session = store.heartbeat(args.session_id)
        return asdict(session) if session else {"error": "Session not found"}

    if cmd == "heartbeat-project":
        sessions = store.heartbeat_project(args.project_slug)
        return {"updated": len(sessions), "session_ids": [s.session_id for s in sessions]}

    if cmd == "complete-session":
        commits = json.loads(args.commits) if args.commits else None
        session = store.complete_session(
            session_id=args.session_id,
            outcome=args.outcome,
            next_steps=args.next_steps or None,
            commits=commits,
            files_changed=args.files_changed or None,
        )
        return asdict(session) if session else {"error": "Session not found"}

    if cmd == "park-session":
        session = store.park_session(
            session_id=args.session_id,
            reason=args.reason,
            next_steps=args.next_steps or None,
        )
        return asdict(session) if session else {"error": "Session not found"}

    if cmd == "resume-session":
        session = store.resume_session(
            session_id=args.session_id,
            new_intent=args.intent,
        )
        return asdict(session)

    if cmd == "active-sessions":
        sessions = store.get_active_sessions(project_slug=args.project)
        return [asdict(s) for s in sessions]

    if cmd == "parked-sessions":
        sessions = store.get_parked_sessions(project_slug=args.project)
        return [asdict(s) for s in sessions]

    if cmd == "stale-sessions":
        sessions = store.get_stale_sessions()
        return [asdict(s) for s in sessions]

    if cmd == "list-sessions":
        status = SessionStatus(args.status) if args.status else None
        sessions = store.list_sessions(
            project_slug=args.project, status=status
        )
        return [asdict(s) for s in sessions[: args.limit]]

    if cmd == "project-state":
        state = store.get_project_state(args.project_slug)
        return asdict(state) if state else {"error": "Project state not found"}

    if cmd == "update-project-state":
        state = store.update_project_state(
            project_slug=args.project_slug,
            current_phase=args.current_phase,
            roadmap_completed=args.completed,
            roadmap_in_progress=args.in_progress,
            roadmap_next_up=args.next_up,
        )
        return asdict(state)

    if cmd == "overview":
        return store.build_overview()

    if cmd == "serve":
        _serve(args.host, args.port)
        return {}  # never reached — uvicorn runs until interrupted

    return {"error": f"Unknown command: {cmd}"}


def _serve(host: str, port: int) -> None:
    """Start the web dashboard via uvicorn."""
    import uvicorn

    web_dir = Path(__file__).parent / "web"
    sys.path.insert(0, str(web_dir))

    print(f"Dashboard: http://{host}:{port}")
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        log_level="warning",
        app_dir=str(web_dir),
    )


if __name__ == "__main__":
    main()
