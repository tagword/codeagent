"""Self reflect tool"""
import logging
from seed_tools.models import Tool
logger = logging.getLogger(__name__)

def self_reflect_tool(summary: str, lesson: str = "") -> str:
    """Append a short reflection to memory/experiences (know-that → trail for know-how).

    存储策略（两层结构）：
      - 有项目上下文 → agents/<id>/projects-data/<project-id>/memory/experiences/
      - 无项目上下文 → agents/<id>/memory/experiences/
    """
    try:
        from seed.agent_context import get_active_llm_session
        from seed.mem_sys import MemorySystem
        from codeagent.core.paths import (
            agent_id_default, agent_memory_dir,
            agent_project_data_subdir,
        )

        aid = agent_id_default()
        from seed.agent_context import active_episodic_project_id, episodic_project_scope_active

        proj = (
            active_episodic_project_id()
            if episodic_project_scope_active()
            else None
        )

        # 根据 project 上下文选择存储路径
        if proj:
            mem_path = agent_project_data_subdir(aid, proj, "memory")
            location = f"projects-data/{proj}/memory/experiences"
        else:
            mem_path = agent_memory_dir(aid)
            location = f"agents/{aid}/memory/experiences"

        m = MemorySystem(base_path=mem_path)
        out = (summary or "").strip()
        les = (lesson or "").strip()
        body = out if not les else f"{out}\n\nHow to improve: {les}"
        m.log_experience(
            task_id="self_reflect",
            outcome=body[:8000],
            tools_used=[],
            session_id=get_active_llm_session(),
            project_id=proj or None,
        )
        return f"Reflection saved to {location}."
    except Exception as e:
        return f"Could not save reflection: {e}"

reflect_def = Tool(
    name="self_reflect",
    description="Save a brief summary and optional lesson to long-term experience logs",
    parameters={
        "summary": {"type": "string", "required": True, "description": "What happened / what worked"},
        "lesson": {
            "type": "string",
            "required": False,
            "description": "Concrete improvement for next time",
        },
    },
    returns="string",
    category="memory",
)

