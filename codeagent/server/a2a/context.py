"""A2A 上下文解析 — contextId / taskId / projectId 的统一入口。

A2A 规范 3.4 节对多轮交互有强制要求：

- 只给 ``taskId`` 时，服务端 **MUST** 从该 Task 反查 ``contextId``
- ``contextId`` 与 ``taskId`` 同时给出但不匹配时，**MUST** 拒绝请求

若不做反查，客户端只传 ``taskId`` 续聊时会被当成新对话，
产生「上下文断裂」——这是比 projectId 丢失更直接的断点。

本模块职责单一：把 A2A 的三个 ID 解析成内部 ``session_id`` + ``project_id``。
不碰 LLM、不碰存储，便于单测。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .models import Message, new_id

logger = logging.getLogger(__name__)

SESSION_PREFIX = "a2a-"


class ContextError(Exception):
    """上下文解析失败（对应 JSON-RPC Invalid params）。"""


@dataclass
class ResolvedContext:
    """解析结果：内部会话标识 + 项目归属。"""

    context_id: str
    task_id: str
    session_id: str
    project_id: str
    #: 是否由 taskId 反查得到（用于调用方可观测性）
    inferred_from_task: bool = False


def resolve(msg: Message, cfg: dict) -> ResolvedContext:
    """把 A2A Message 解析为内部上下文。

    优先级：
    - ``contextId``：message.contextId → 由 taskId 反查 → 新建
    - ``projectId``：message.metadata.projectId → configuration.projectId → 空
    """
    context_id = msg.context_id.strip()
    task_id = msg.task_id.strip()
    inferred = False

    if not context_id and task_id:
        found = context_id_for_task(task_id)
        if found:
            context_id = found
            inferred = True
        else:
            # 规范：无法反查时不能静默新建同名上下文，否则会串话。
            logger.warning("a2a: taskId=%s 无法反查 contextId，按新上下文处理", task_id)
    elif context_id and task_id:
        _assert_match(context_id, task_id)

    if not context_id:
        context_id = new_id("ctx")
    if not task_id:
        task_id = new_id("task")

    project_id = msg.project_id() or str(cfg.get("projectId") or "").strip()
    if project_id:
        project_id = _validated_project_id(project_id, str(cfg.get("agentId") or "default"))
    else:
        # 续聊未显式指定项目时，沿用该会话已归属的项目，
        # 否则会话会被搬回未分类，造成归属漂移。
        project_id = _inherited_project_id(
            f"{SESSION_PREFIX}{context_id}", str(cfg.get("agentId") or "default")
        )

    return ResolvedContext(
        context_id=context_id,
        task_id=task_id,
        session_id=f"{SESSION_PREFIX}{context_id}",
        project_id=project_id,
        inferred_from_task=inferred,
    )


def _validated_project_id(project_id: str, agent_id: str) -> str:
    """校验项目是否真实存在，不存在则降级为空（归入未分类）。

    背景：``persist_chat_session`` 注册会话时依赖 registry 外键，
    项目不存在会抛 ``IntegrityError``，而 chat_turn 内的持久化异常
    被吞掉，结果是**会话静默丢失**。A2A 是外部调用入口，
    projectId 不可信，必须在入口处校验。
    """
    if not project_id:
        return ""
    try:
        from seed.core.proj_reg import get_project

        if get_project(agent_id, project_id):
            return project_id
        logger.warning(
            "a2a: projectId=%s 不存在，降级为未分类（避免会话持久化失败）", project_id
        )
    except Exception:  # noqa: BLE001
        logger.warning("a2a: projectId 校验异常，降级为未分类", exc_info=True)
    return ""


def _assert_match(context_id: str, task_id: str) -> None:
    """规范 MUST：contextId 与 taskId 指向的上下文不一致时拒绝。"""
    actual = context_id_for_task(task_id)
    if actual and actual != context_id:
        raise ContextError(
            f"contextId/taskId mismatch: task {task_id} belongs to {actual}, got {context_id}"
        )


def context_id_for_task(task_id: str, agent_id: str = "default") -> str:
    """从 taskId 反查 contextId。

    当前 Task 无独立存储（零侵入设计），taskId 与 contextId 的绑定
    记录在会话文件 metadata 的 ``a2a_tasks`` 列表里。查不到返回空串。

    实现要点：
    - 会话可能落在 ``projects-data/<pid>/sessions/`` 或 ``agents/<id>/sessions/``，
      且新版为目录式存储（``_audit/<session>/``），**不能假设平铺 JSON**。
      因此先经 registry 拿到会话 ID 列表，再用官方加载器逐个读取。
    - registry 的 ``_extract_session_meta`` 只透传白名单字段，
      自定义 ``a2a_tasks`` 会被丢弃，故必须读会话本体。
    """
    if not task_id:
        return ""
    try:
        from seed.core.llm_sess import (
            list_stored_sessions_meta,
            load_chat_session_from_disk,
        )

        for meta in list_stored_sessions_meta(limit=300, agent_id=agent_id):
            sid = str(meta.get("session_id") or meta.get("id") or "").strip()
            if not sid.startswith(SESSION_PREFIX):
                continue
            pid = str(meta.get("project_id") or "").strip()
            sess = load_chat_session_from_disk(sid, agent_id=agent_id, project_id=pid or None)
            if sess is None:
                continue
            md = sess.metadata if isinstance(sess.metadata, dict) else {}
            if task_id in (md.get("a2a_tasks") or []):
                return sid[len(SESSION_PREFIX):]
    except Exception:  # noqa: BLE001
        logger.debug("a2a: taskId 反查失败", exc_info=True)
    return ""


def record_task(
    session_id: str, task_id: str, agent_id: str = "default", project_id: str = ""
) -> None:
    """把 taskId 登记到会话 metadata，供后续 ``taskId`` 反查。

    保留最近 50 条，避免长会话 metadata 无限膨胀。
    ``project_id`` 必须传入——会话可能存放在项目目录下，
    不传会导致加载不到、登记静默失败。
    """
    if not task_id:
        return
    try:
        from seed.core.llm_sess import load_chat_session_from_disk, persist_chat_session

        sess = load_chat_session_from_disk(
            session_id, agent_id=agent_id, project_id=project_id or None
        )
        if sess is None:
            logger.warning("a2a: 登记 taskId 失败，会话不存在 session=%s", session_id)
            return
        md = sess.metadata if isinstance(sess.metadata, dict) else {}
        tasks = [str(t) for t in (md.get("a2a_tasks") or [])]
        if task_id in tasks:
            return
        tasks.append(task_id)
        md["a2a_tasks"] = tasks[-50:]
        sess.metadata = md
        persist_chat_session(sess, agent_id)
    except Exception:  # noqa: BLE001
        logger.warning("a2a: 登记 taskId 异常", exc_info=True)


def _inherited_project_id(session_id: str, agent_id: str) -> str:
    """读取已有会话的项目归属（续聊时继承，避免归属漂移）。"""
    try:
        from seed.core.llm_sess import load_chat_session_from_disk

        sess = load_chat_session_from_disk(session_id, agent_id=agent_id)
        if sess is None:
            return ""
        md = sess.metadata if isinstance(sess.metadata, dict) else {}
        return str(md.get("project_id") or "").strip()
    except Exception:  # noqa: BLE001
        return ""
