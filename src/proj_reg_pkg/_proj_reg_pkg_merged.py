"""Web UI project registry per agent (agents/<id>/projects/registry.json).

每个项目可关联一个文件系统目录（path），用于文件树和 Git 操作。

两层结构：
  - 用户层：path（源代码目录，由用户定义）
  - Agent 层：agent_data_dir（会话/记忆/产物/计划/待办，系统自动管理）

Agent 数据目录结构：
  projects-data/<project-id>/
    ├── plans/         ← *.plan.md 规划文档
    ├── sessions/      ← 该项目的对话会话
    ├── artifacts/     ← 中间产物
    ├── memory/        ← 项目相关记忆
    └── todos/         ← 待办事项
"""
from __future__ import annotations


import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.codeagent.core.paths import (
    agent_projects_registry_dir,
    agent_project_data_dir,
)


def _registry_path(agent_id: str) -> Path:
    return agent_projects_registry_dir(agent_id) / "registry.json"


def _ensure_agent_data_dirs(agent_id: str, project_id: str) -> Path:
    """创建 Agent 层项目数据目录结构并返回根目录。"""
    root = agent_project_data_dir(agent_id, project_id)
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("plans", "sessions", "artifacts", "memory", "todos"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def list_projects(agent_id: str) -> List[Dict[str, Any]]:
    """列出项目，每个项目含 id / name / path / agent_data_dir / created_at"""
    p = _registry_path(agent_id)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = data.get("projects")
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        pid = str(r.get("id") or "").strip()
        name = str(r.get("name") or "").strip()
        if not pid or not name:
            continue
        out.append({
            "id": pid,
            "name": name,
            "path": str(r.get("path") or ""),
            "agent_data_dir": str(r.get("agent_data_dir") or agent_project_data_dir(agent_id, pid)),
            "created_at": str(r.get("created_at") or ""),
        })
    return out


def create_project(agent_id: str, name: str, path: str = "") -> Dict[str, Any]:
    """创建项目，可选关联文件系统目录。

    自动创建 Agent 层数据目录（plans/ sessions/ artifacts/ memory/ todos/）。
    """
    raw = (name or "").strip()
    if not raw:
        raise ValueError("project name required")
    p = _registry_path(agent_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {"projects": []}
    else:
        data = {"projects": []}
    rows = data.get("projects")
    if not isinstance(rows, list):
        rows = []
    pid = uuid.uuid4().hex

    # 创建 Agent 层数据目录
    agent_data = _ensure_agent_data_dirs(agent_id, pid)

    row: Dict[str, Any] = {
        "id": pid,
        "name": raw[:120],
        "agent_data_dir": str(agent_data),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if path:
        row["path"] = os.path.abspath(path)
    rows.append(row)
    data["projects"] = rows
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)
    return row




import json
import os
from typing import Optional, Dict, Any

def get_project(agent_id: str, project_id: str) -> Optional[Dict[str, Any]]:
    """获取单个项目信息。"""
    for proj in list_projects(agent_id):
        if proj["id"] == project_id:
            return proj
    return None


def update_project_data_dir(agent_id: str, project_id: str) -> bool:
    """为已有项目补全 agent_data_dir 字段（用于迁移/升级）。"""
    pid = (project_id or "").strip()
    if not pid:
        return False
    p = _registry_path(agent_id)
    if not p.is_file():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    rows = data.get("projects")
    if not isinstance(rows, list):
        return False
    found = False
    for r in rows:
        if isinstance(r, dict) and str(r.get("id") or "").strip() == pid:
            if not r.get("agent_data_dir"):
                r["agent_data_dir"] = str(_ensure_agent_data_dirs(agent_id, pid))
            found = True
            break
    if not found:
        return False
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)
    return True


def update_project_path(agent_id: str, project_id: str, path: str) -> bool:
    """更新项目的文件系统路径。"""
    pid = (project_id or "").strip()
    pval = (path or "").strip()
    if not pid:
        return False
    p = _registry_path(agent_id)
    if not p.is_file():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    rows = data.get("projects")
    if not isinstance(rows, list):
        return False
    found = False
    for r in rows:
        if isinstance(r, dict) and str(r.get("id") or "").strip() == pid:
            r["path"] = os.path.abspath(pval)
            found = True
            break
    if not found:
        return False
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)
    return True


def rename_project(agent_id: str, project_id: str, new_name: str) -> bool:
    """重命名项目。"""
    pid = (project_id or "").strip()
    name = (new_name or "").strip()
    if not pid or not name:
        return False
    p = _registry_path(agent_id)
    if not p.is_file():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    rows = data.get("projects")
    if not isinstance(rows, list):
        return False
    found = False
    for r in rows:
        if isinstance(r, dict) and str(r.get("id") or "").strip() == pid:
            r["name"] = name[:120]
            found = True
            break
    if not found:
        return False
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)
    return True




import json
from pathlib import Path
from typing import List
from src.codeagent.core.paths import agent_project_data_dir

def delete_project(agent_id: str, project_id: str) -> bool:
    """删除项目。"""
    pid = (project_id or "").strip()
    if not pid:
        return False
    p = _registry_path(agent_id)
    if not p.is_file():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    rows = data.get("projects")
    if not isinstance(rows, list):
        return False
    n = len(rows)
    rows = [r for r in rows if not (isinstance(r, dict) and str(r.get("id") or "").strip() == pid)]
    if len(rows) == n:
        return False
    data["projects"] = rows
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)
    return True


def get_project_data_dir(agent_id: str, project_id: str) -> str:
    """获取项目的 Agent 数据目录路径（从 registry 读取或按规则推算）。"""
    proj = get_project(agent_id, project_id)
    if proj and proj.get("agent_data_dir"):
        d = proj["agent_data_dir"]
        # 确保目录存在
        Path(d).mkdir(parents=True, exist_ok=True)
        return d
    # 按规则推算
    d = agent_project_data_dir(agent_id, project_id)
    _ensure_agent_data_dirs(agent_id, project_id)
    return str(d)


def get_project_data_subdir(agent_id: str, project_id: str, sub: str) -> str:
    """获取项目数据子目录，如 sessions/ artifacts/ plans/ memory/ todos/"""
    root = get_project_data_dir(agent_id, project_id)
    d = Path(root) / sub
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def list_project_session_ids(agent_id: str, project_id: str) -> List[str]:
    """列出项目下的会话文件 ID（不带 .json 后缀）。"""
    sess_dir = Path(get_project_data_subdir(agent_id, project_id, "sessions"))
    if not sess_dir.is_dir():
        return []
    return sorted(
        (f.stem for f in sess_dir.glob("*.json")),
        key=lambda s: sess_dir / f"{s}.json",
    )


def list_project_plan_files(agent_id: str, project_id: str) -> List[str]:
    """列出项目下的规划文件。"""
    plans_dir = Path(get_project_data_subdir(agent_id, project_id, "plans"))
    if not plans_dir.is_dir():
        return []
    return sorted(str(p.relative_to(plans_dir)) for p in plans_dir.glob("*") if p.is_file())
