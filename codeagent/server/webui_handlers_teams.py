"""Web UI team / hub / run endpoints — split out of ``webui_api_app``.

Mounted at ``/api/ui``. Team metadata helpers come from
``webui_handlers_agentmeta``; hub and team-engine functions are imported lazily
inside handlers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from .webui_handlers_agentmeta import _list_team_metas, _teams_dir

logger = logging.getLogger(__name__)


def build_teams_routes(project_root: Path) -> list[Route]:
    """Return the team / hub / run routes for ``webui_api_app``."""

    async def api_hub_send(request: Request) -> JSONResponse:
        """POST /api/hub/send — send a message to the hub."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        frm = (body.get("frm") or body.get("from") or "").strip()
        to = (body.get("to") or "").strip()
        content = (body.get("content") or body.get("message") or "").strip()
        if not frm or not content:
            return JSONResponse({"detail": "frm and content are required"}, status_code=400)
        from codeagent.server.hub import send_message
        msg = send_message(frm, to or "all", content)
        return JSONResponse({"message": msg})

    async def api_hub_events(request: Request) -> JSONResponse:
        """GET /api/hub/events — SSE stream of hub messages."""
        last_event_id = (request.headers.get("last-event-id") or
                         request.query_params.get("lastEventId") or
                         request.query_params.get("last_id") or None)
        from codeagent.server.hub import sse_generator, subscribe
        sid, q = subscribe()
        logger.info("hub SSE subscriber %s connected (last_id=%s)", sid, last_event_id)
        return StreamingResponse(
            sse_generator(sid, q, last_event_id=last_event_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def api_hub_messages(request: Request) -> JSONResponse:
        """GET /api/hub/messages — list recent hub messages."""
        limit_s = request.query_params.get("limit", "50")
        try:
            limit = int(limit_s)
        except ValueError:
            limit = 50
        filter_agent = request.query_params.get("agent_id") or None
        from codeagent.server.hub import load_messages
        msgs = load_messages(limit=limit, filter_agent=filter_agent)
        return JSONResponse({"messages": msgs})

    # ── Team CRUD ───────────────────────────────────────────────

    async def api_teams_list(_: Request) -> JSONResponse:
        teams = _list_team_metas()
        return JSONResponse({"teams": teams})

    async def api_teams_create(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        team_id = (body.get("id") or "").strip()
        if not team_id:
            return JSONResponse({"detail": "team id is required"}, status_code=400)
        td = _teams_dir()
        team_file = td / f"{team_id}.json"
        if team_file.exists():
            return JSONResponse({"detail": f"team '{team_id}' already exists"}, status_code=409)
        team_data = {
            "name": body.get("name", team_id),
            "description": body.get("description", ""),
            "members": body.get("members", []),
            "manager_id": body.get("manager_id", ""),
            "mode": body.get("mode", "sequential"),
            "error_policy": body.get("error_policy", "stop"),
            "timeout_seconds": body.get("timeout_seconds", 300),
        }
        td.mkdir(parents=True, exist_ok=True)
        team_file.write_text(json.dumps(team_data, indent=2, ensure_ascii=False), encoding="utf-8")
        team_data["id"] = team_id
        return JSONResponse({"team": team_data}, status_code=201)

    async def api_teams_get(request: Request) -> JSONResponse:
        team_id = request.path_params.get("team_id", "")
        team_file = _teams_dir() / f"{team_id}.json"
        if not team_file.is_file():
            return JSONResponse({"detail": "team not found"}, status_code=404)
        try:
            data = json.loads(team_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return JSONResponse({"detail": "invalid team data"}, status_code=500)
        data["id"] = team_id
        return JSONResponse({"team": data})

    async def api_teams_update(request: Request) -> JSONResponse:
        team_id = request.path_params.get("team_id", "")
        team_file = _teams_dir() / f"{team_id}.json"
        if not team_file.is_file():
            return JSONResponse({"detail": "team not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        try:
            data = json.loads(team_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        for k in ("name", "description", "members", "manager_id", "mode", "error_policy", "timeout_seconds"):
            if k in body:
                data[k] = body[k]
        team_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        data["id"] = team_id
        return JSONResponse({"team": data})

    async def api_teams_delete(request: Request) -> JSONResponse:
        team_id = request.path_params.get("team_id", "")
        team_file = _teams_dir() / f"{team_id}.json"
        if not team_file.is_file():
            return JSONResponse({"detail": "team not found"}, status_code=404)
        team_file.unlink()
        return JSONResponse({"detail": "deleted"})

    # ── Team Run ────────────────────────────────────────────────

    async def api_teams_run(request: Request) -> JSONResponse:
        """Execute a team workflow asynchronously."""
        team_id = request.path_params.get("team_id", "")
        tf = _teams_dir() / f"{team_id}.json"
        if not tf.is_file():
            return JSONResponse({"detail": "team not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        user_input = (body.get("input") or body.get("user_input") or "").strip()
        if not user_input:
            return JSONResponse({"detail": "input is required"}, status_code=400)
        try:
            from codeagent.server.team_engine import run_team
            run = run_team(team_id, user_input)
            return JSONResponse({"run": run})
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        except Exception as e:
            logger.exception("team run failed")
            return JSONResponse({"detail": f"run failed: {e}"}, status_code=500)

    async def api_runs_list(request: Request) -> JSONResponse:
        team_id = request.query_params.get("team_id", "")
        from codeagent.server.team_engine import list_runs
        runs = list_runs(team_id=team_id or None)
        return JSONResponse({"runs": runs})

    async def api_runs_get(request: Request) -> JSONResponse:
        run_id = request.path_params.get("run_id", "")
        from codeagent.server.team_engine import get_run
        run = get_run(run_id)
        if run is None:
            return JSONResponse({"detail": "run not found"}, status_code=404)
        return JSONResponse({"run": run})

    async def api_runs_cancel(request: Request) -> JSONResponse:
        """POST /api/ui/runs/{run_id}/cancel — force-stop a running run."""
        run_id = request.path_params.get("run_id", "")
        from codeagent.server.team_engine import cancel_run
        updated = cancel_run(run_id)
        if updated is None:
            return JSONResponse({"detail": "run not found"}, status_code=404)
        return JSONResponse({"detail": f"run {run_id} stopped", "run": updated})

    # ── Health / Watchdog ──────────────────────────────────────

    async def api_runs_recover(request: Request) -> JSONResponse:
        """POST /api/ui/runs/{run_id}/recover — re-execute a failed/timeout run."""
        run_id = request.path_params.get("run_id", "")
        from codeagent.server.team_engine import get_run, rerun_run
        run = get_run(run_id)
        if run is None:
            return JSONResponse({"detail": "run not found"}, status_code=404)
        if run.get("status") not in ("failed", "timeout"):
            return JSONResponse({"detail": "only failed/timeout runs can be recovered"}, status_code=400)
        updated = rerun_run(run_id)
        if updated is None:
            return JSONResponse({"detail": "run not found"}, status_code=404)
        return JSONResponse({"detail": f"run {run_id} re-executing", "run": updated})

    # ── Routes ─────────────────────────────────────────────────


    return [
        Route("/teams", api_teams_list, methods=["GET"]),
        Route("/teams", api_teams_create, methods=["POST"]),
        Route("/teams/{team_id}", api_teams_get, methods=["GET"]),
        Route("/teams/{team_id}", api_teams_update, methods=["PUT"]),
        Route("/teams/{team_id}", api_teams_delete, methods=["DELETE"]),
        Route("/teams/{team_id}/run", api_teams_run, methods=["POST"]),
        Route("/runs", api_runs_list, methods=["GET"]),
        Route("/runs/{run_id}", api_runs_get, methods=["GET"]),
        Route("/runs/{run_id}/recover", api_runs_recover, methods=["POST"]),
        Route("/runs/{run_id}/cancel", api_runs_cancel, methods=["POST"]),
        Route("/hub/send", api_hub_send, methods=["POST"]),
        Route("/hub/events", api_hub_events, methods=["GET"]),
        Route("/hub/messages", api_hub_messages, methods=["GET"]),
    ]
