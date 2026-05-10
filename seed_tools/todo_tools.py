"""Tool module: todo_tools"""
import logging
from seed_tools.models import Tool

logger = logging.getLogger(__name__)

def todo_tool_handler(
    operation: str,
    content: str = "",
    todo_id: str = "",
    status: str = "",
    scope: str = "session",
) -> str:
    """Manage project-scoped todo items. scope='session' (default) only
    accesses the current conversation's todos; scope='project' accesses
    todos from all sessions in this project."""
    try:
        from seed.proj_todos import list_todos, create_todo, update_todo, delete_todo
        from seed.agent_context import active_episodic_project_id, get_active_llm_session

        pid = active_episodic_project_id()
        if not pid:
            return "错误：当前会话未关联项目，无法管理待办事项。请先选择一个或新建一个项目。"

        sc = (scope or "").strip().lower()
        if sc not in ("session", "project"):
            return "错误：scope 参数只能是 session（当前会话）或 project（项目全部）。"

        # Get current session ID — used for session-scoped operations
        current_sid = get_active_llm_session() or ""
        # server.py stores compound key "agent_id::session_id" via
        # set_active_llm_session(mkey).  Extract the raw session_id.
        if "::" in current_sid:
            current_sid = current_sid.split("::", 1)[-1]

        op = (operation or "").strip().lower()
        if op == "create":
            c = (content or "").strip()
            if not c:
                return "错误：创建 todo 需要 content 参数。"
            item = create_todo("default", pid, content=c, session_id=current_sid)
            scope_label = "" if sc == "project" else "（当前会话）"
            return f"已创建待办事项{scope_label}：{item['content']}（ID: {item['id']}）"

        if op == "list":
            st = (status or "").strip().lower() or None
            if sc == "session":
                rows = list_todos("default", pid, status=st, session_id=current_sid)
            else:
                rows = list_todos("default", pid, status=st)
            if not rows:
                if sc == "session":
                    return "当前会话暂无待办事项。" if not st else f"当前会话没有状态为「{st}」的待办事项。"
                return "当前项目暂无待办事项。" if not st else f"没有状态为「{st}」的待办事项。"
            scope_label = "当前会话" if sc == "session" else "当前项目"
            parts = []
            for r in rows:
                label = {"pending": "待办", "in_progress": "进行中", "completed": "已完成", "cancelled": "已取消"}.get(r.get("status", ""), r.get("status", ""))
                parts.append(f"- [{label}] {r['content']} (ID: {r['id']})")
            return f"{scope_label}待办事项：\n" + "\n".join(parts) + f"\n\n共 {len(rows)} 项。"

        if op == "update":
            tid = (todo_id or "").strip()
            if not tid:
                return "错误：更新 todo 需要 todo_id 参数。"
            up = {}
            if content:
                up["content"] = content
            if status:
                up["status"] = status
            if not up:
                return "错误：更新 todo 至少需要提供 content 或 status。"
            item = update_todo("default", pid, tid, up)
            if item is None:
                return f"未找到 ID 为「{tid}」的待办事项。"
            return f"已更新待办事项：{item['content']}（状态: {item['status']}）"

        if op == "delete":
            tid = (todo_id or "").strip()
            if not tid:
                return "错误：删除 todo 需要 todo_id 参数。"
            ok = delete_todo("default", pid, tid)
            if not ok:
                return f"未找到 ID 为「{tid}」的待办事项。"
            return f"已删除待办事项（ID: {tid}）。"

        return f"错误：不支持的 operation「{op}」，支持: create, list, update, delete。"
    except Exception as e:
        return f"待办事项操作出错：{e}"

todo_tool_def = Tool(
    name="todo_tool",
    description="项目范围的待办事项管理工具，支持创建/查询/更新/删除操作。operation 参数指定操作类型（create/list/update/delete），其他参数按需传入。scope 参数控制操作范围：session（默认，仅当前会话）或 project（项目全部）。",
    parameters={
        "operation": {
            "type": "string",
            "required": True,
            "description": "操作类型：create（创建）/ list（查询）/ update（更新）/ delete（删除）",
        },
        "content": {
            "type": "string",
            "required": False,
            "description": "待办内容（create 时必填；update 时可选用于修改内容）",
        },
        "todo_id": {
            "type": "string",
            "required": False,
            "description": "待办 ID（update / delete 时必填）",
        },
        "status": {
            "type": "string",
            "required": False,
            "description": "状态值：pending / in_progress / completed / cancelled（list 时可作为过滤条件，update 时可修改状态）",
        },
        "scope": {
            "type": "string",
            "required": False,
            "description": "操作范围：session（默认，仅当前会话的待办）或 project（项目全部会话的待办）",
        },
    },
    returns="string: 操作结果描述"
)

# Claw-code Tool 5: ToolSearcherTool - Tool search

