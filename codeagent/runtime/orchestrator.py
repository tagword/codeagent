"""Orchestrator: split tasks and dispatch to workers (parallel or sequential)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from .task_split import auto_split_enabled, split_user_tasks
from .worker import Worker

logger = logging.getLogger(__name__)


@dataclass
class Orchestrator:
    """
    Dispatch user work to one or more workers.

    - Default: first worker, single task.
    - ``metadata["subtasks"]``: explicit list of prompts.
    - ``metadata["parallel"]=true`` or multiple workers + auto-split: parallel run.
    """

    workers: list[Worker] = field(default_factory=list)
    parallel: bool = False

    def run(
        self,
        *,
        session_id: str,
        user_text: str,
        max_tool_rounds: int = 16,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if not self.workers:
            raise RuntimeError("Orchestrator has no workers configured")

        meta = dict(metadata or {})
        subtasks = meta.get("subtasks")
        if isinstance(subtasks, list):
            tasks = [str(t).strip() for t in subtasks if str(t).strip()]
        else:
            tasks = []

        if not tasks and auto_split_enabled(meta.get("auto_split")):
            tasks = split_user_tasks(user_text)

        if not tasks:
            tasks = [user_text]

        if "parallel" in meta:
            use_parallel = bool(meta.get("parallel"))
        else:
            use_parallel = bool(
                self.parallel and len(tasks) > 1 and len(self.workers) > 1
            )

        if len(tasks) == 1:
            reply, wmeta = self.workers[0].run(
                session_id=session_id,
                user_text=tasks[0],
                max_tool_rounds=max_tool_rounds,
            )
            out_meta = dict(wmeta or {})
            out_meta["orchestrator"] = {"mode": "single", "tasks": 1}
            return reply, out_meta

        if use_parallel and len(self.workers) > 1:
            return self._run_parallel(
                tasks,
                session_id=session_id,
                max_tool_rounds=max_tool_rounds,
                meta=meta,
            )
        return self._run_sequential(
            tasks,
            session_id=session_id,
            max_tool_rounds=max_tool_rounds,
            meta=meta,
        )

    def _run_sequential(
        self,
        tasks: list[str],
        *,
        session_id: str,
        max_tool_rounds: int,
        meta: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        parts: list[str] = []
        metas: list[dict[str, Any]] = []
        for i, task in enumerate(tasks):
            worker = self.workers[i % len(self.workers)]
            sub_sid = f"{session_id}::sub{i}"
            reply, wmeta = worker.run(
                session_id=sub_sid,
                user_text=task,
                max_tool_rounds=max_tool_rounds,
            )
            parts.append(f"### Subtask {i + 1}\n\n{reply}")
            metas.append(wmeta or {})
        merged = "\n\n".join(parts)
        return merged, {
            "orchestrator": {
                "mode": "sequential",
                "tasks": len(tasks),
                "workers_used": len(self.workers),
            },
            "subtask_meta": metas,
            **meta,
        }

    def _run_parallel(
        self,
        tasks: list[str],
        *,
        session_id: str,
        max_tool_rounds: int,
        meta: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        results: dict[int, tuple[str, dict[str, Any]]] = {}
        max_workers = min(len(tasks), len(self.workers), 8)

        def _job(i: int, task: str) -> tuple[int, str, dict[str, Any]]:
            worker = self.workers[i % len(self.workers)]
            sub_sid = f"{session_id}::sub{i}"
            reply, wmeta = worker.run(
                session_id=sub_sid,
                user_text=task,
                max_tool_rounds=max_tool_rounds,
            )
            return i, reply, wmeta or {}

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_job, i, t) for i, t in enumerate(tasks)]
            for fut in as_completed(futures):
                try:
                    i, reply, wmeta = fut.result()
                    results[i] = (reply, wmeta)
                except Exception as e:
                    logger.exception("orchestrator subtask failed")
                    results[len(results)] = (f"[subtask error] {e}", {})

        parts = []
        metas = []
        for i in sorted(results.keys()):
            reply, wmeta = results[i]
            parts.append(f"### Subtask {i + 1}\n\n{reply}")
            metas.append(wmeta)
        merged = "\n\n".join(parts)
        return merged, {
            "orchestrator": {
                "mode": "parallel",
                "tasks": len(tasks),
                "workers_used": max_workers,
            },
            "subtask_meta": metas,
            **meta,
        }
