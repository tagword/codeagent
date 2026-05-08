"""Tool module: search_tools"""
import logging
from src.models_pkg import Tool

logger = logging.getLogger(__name__)

def tool_search_handler(query: str) -> str:
    """Search available tools by name or description"""
    import json

    try:
        from src.tools import setup_builtin_tools

        registry, _ = setup_builtin_tools()
        results = []
        query_lower = query.lower()

        for tool_name, tool in registry.tools.items():
            if query_lower in tool_name.lower() or query_lower in tool.description.lower():
                results.append({
                    "name": tool_name,
                    "description": tool.description,
                    "parameters": tool.parameters
                })
        
        return json.dumps(results if results else [{"message": f"No tools found matching '{query}'"}])
    except Exception as e:
        return json.dumps([{"error": f"Error searching tools: {e}"}])

tool_search_def = Tool(
    name="tool_search_tool",
    description="Search available tools by name or description",
    parameters={
        "query": {"type": "string", "required": True, "description": "Search query"}
    },
    returns="list[dict]: Matching tools with metadata"
)

# Claw-code Tool 6: WebSearcherTool - Web search

