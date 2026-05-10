"""Tool registration helpers"""
from dataclasses import replace
import logging

from seed.models import Tool
from seed.tools.executor import ToolExecutor
from seed.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# ── Import all tool modules ──
from seed.tools.misc_tools import (
    echo_tool, echo_tool_def, calculate_tool, calc_tool_def,
    counter_tool, counter_tool_def, whoami_tool, whoami_tool_def,
    wbs_draft_tool, wbs_def, workspace_verify_handler, workspace_verify_def,
)
from seed.tools.file_read_tools import file_read_handler, file_read_def
from seed.tools.file_write_tools import (
    file_write_handler, file_write_def, file_edit_handler, file_edit_def,
    file_search_handler, file_search_def, glob_tool_handler, glob_tool_def,
    grep_tool_handler, grep_tool_def,
)
from seed.tools.artifact_tools import artifact_read_handler, artifact_read_def
from seed.tools.web_tools import web_fetch_handler, web_fetch_def, web_search_handler, web_search_def
from seed.tools.code_analyze_tools import (
    code_analyze_handler,
    code_analyze_def,
    code_check_handler,
    code_check_def,
)
from seed.tools.todo_tools import todo_tool_handler, todo_tool_def
from seed.tools.search_tools import tool_search_handler, tool_search_def
from seed.tools.notebook_tools import notebook_edit_handler, notebook_edit_def
from seed.tools.memory_search_tools import memory_search_handler, memory_search_def
from seed.tools.self_reflect_tools import self_reflect_tool, reflect_def
from seed.tools.cron_query_tools import codeagent_cron_path_handler, codeagent_cron_path_def
from seed.tools.cron_query_tools import codeagent_cron_reload_handler, codeagent_cron_reload_def
from seed.tools.cron_apply_tools import codeagent_cron_apply_handler, codeagent_cron_apply_def
from seed.tools.hub_tools import hub_send, hub_send_def
from seed.tools.git_a import git_tool_handler
from seed.tools.browser_a import (
    browser_status,
    browser_status_def,
    browser_connect,
    browser_connect_def,
    browser_ensure_running,
    browser_ensure_running_def,
    browser_targets,
    browser_targets_def,
    browser_new_page,
    browser_new_page_def,
    browser_navigate,
    browser_navigate_def,
    browser_screenshot,
    browser_screenshot_def,
)
from seed.tools.shell_tool import bash_def, bash_tool_handler

# ── Migrated tool_modules tools ──
from seed.tools.refactor_tools import refactor_handler, refactor_tool_def
from seed.tools.diagram_tools import diagram_handler, diagram_tool_def
from seed.tools.api_docs_tools import api_docs_handler, api_docs_tool_def
from seed.tools.scaffold_tools import scaffold_handler, scaffold_tool_def
from seed.tools.project_tools import project_handler, project_tool_def
from seed.tools.db_tools import db_handler, db_tool_def
from seed.tools.deps_check_tools import deps_check_handler, deps_check_tool_def
from seed.tools.test_gen_tools import test_gen_handler, test_gen_tool_def
from seed.tools.pipeline_tools import pipeline_handler, pipeline_tool_def
from seed.tools.deploy_tools import deploy_handler, deploy_tool_def

# ── Create missing tool definitions ──
git_tool_def = Tool(
    name="git",
    description="Git operations tool",
    parameters={
        "command": {"type": "string", "required": True, "description": "Git subcommand"},
        "args": {"type": "string", "required": False, "description": "Arguments"},
        "message": {"type": "string", "required": False, "description": "Commit message"},
    },
    returns="string",
    category="git",
)


def setup_builtin_tools():
    """Setup and register all builtin tools."""
    registry = ToolRegistry()
    
    # Misc tools
    registry.register(echo_tool_def, echo_tool)
    registry.register(calc_tool_def, calculate_tool)
    registry.register(counter_tool_def, counter_tool)
    registry.register(whoami_tool_def, whoami_tool)
    registry.register(wbs_def, wbs_draft_tool)
    registry.register(workspace_verify_def, workspace_verify_handler)

    # Shell (bash_tool + bash_exec alias for prompts / acquired-tool policy)
    registry.register(bash_def, bash_tool_handler)
    registry.register(
        replace(
            bash_def,
            name="bash_exec",
            description=(
                "Execute shell commands with safety checks (same implementation as bash_tool; "
                "use acquired tools policy to enable)."
            ),
        ),
        bash_tool_handler,
    )

    # File tools
    registry.register(file_read_def, file_read_handler)
    registry.register(file_write_def, file_write_handler)
    registry.register(file_edit_def, file_edit_handler)
    registry.register(file_search_def, file_search_handler)
    registry.register(glob_tool_def, glob_tool_handler)
    registry.register(grep_tool_def, grep_tool_handler)
    
    # Artifact tools
    registry.register(artifact_read_def, artifact_read_handler)
    
    # Web tools
    registry.register(web_fetch_def, web_fetch_handler)
    registry.register(web_search_def, web_search_handler)
    
    # Code tools
    registry.register(code_check_def, code_check_handler)
    registry.register(code_analyze_def, code_analyze_handler)
    
    # Todo tools
    registry.register(todo_tool_def, todo_tool_handler)
    
    # Search tools
    registry.register(tool_search_def, tool_search_handler)
    
    # Notebook tools
    registry.register(notebook_edit_def, notebook_edit_handler)
    
    # Memory tools
    registry.register(memory_search_def, memory_search_handler)
    registry.register(reflect_def, self_reflect_tool)
    
    # Cron tools
    registry.register(codeagent_cron_path_def, codeagent_cron_path_handler)
    registry.register(codeagent_cron_reload_def, codeagent_cron_reload_handler)
    registry.register(codeagent_cron_apply_def, codeagent_cron_apply_handler)
    
    # Git tool
    registry.register(git_tool_def, git_tool_handler)
    
    # Hub tools
    registry.register(hub_send_def, hub_send)
    
    # Browser tools
    registry.register(browser_status_def, browser_status)
    registry.register(browser_connect_def, browser_connect)
    registry.register(browser_ensure_running_def, browser_ensure_running)
    registry.register(browser_targets_def, browser_targets)
    registry.register(browser_new_page_def, browser_new_page)
    registry.register(browser_navigate_def, browser_navigate)
    registry.register(browser_screenshot_def, browser_screenshot)

    # ── Migrated tool_modules (dev tools) ──
    registry.register(project_tool_def, project_handler)
    registry.register(refactor_tool_def, refactor_handler)
    registry.register(scaffold_tool_def, scaffold_handler)
    registry.register(test_gen_tool_def, test_gen_handler)
    registry.register(deploy_tool_def, deploy_handler)
    registry.register(deps_check_tool_def, deps_check_handler)
    registry.register(api_docs_tool_def, api_docs_handler)
    registry.register(diagram_tool_def, diagram_handler)
    registry.register(pipeline_tool_def, pipeline_handler)
    registry.register(db_tool_def, db_handler)
    
    executor = ToolExecutor(registry)
    return registry, executor

