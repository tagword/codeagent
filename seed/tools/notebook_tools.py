"""Tool module: notebook_tools"""
import logging
from seed.models import Tool

logger = logging.getLogger(__name__)

def notebook_edit_handler(filepath: str, cell_index: int, cell_code: str, cell_type: str = "code") -> str:
    """Edit cells in a Jupyter notebook"""
    try:
        import json
        import os
        
        if not os.path.exists(filepath):
            if not filepath.endswith('.ipynb'):
                return f"Error: Not a notebook file: {filepath}"
            return f"Error: Notebook file not found: {filepath}"
        
        with open(filepath, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        
        if cell_index < 0 or cell_index >= len(notebook['cells']):
            return f"Error: Invalid cell index {cell_index}. Notebook has {len(notebook['cells'])} cells."
        
        notebook['cells'][cell_index]['source'] = cell_code.split('\n')
        if cell_type in ['markdown', 'code', 'raw']:
            notebook['cells'][cell_index]['cell_type'] = cell_type
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(notebook, f, indent=2)
        
        return f"Successfully updated cell {cell_index} in {filepath}"
    except Exception as e:
        return f"Error editing notebook: {e}"

notebook_edit_def = Tool(
    name="notebook_edit_tool",
    description="Edit cells in a Jupyter notebook",
    parameters={
        "filepath": {"type": "string", "required": True, "description": "Path to the .ipynb file"},
        "cell_index": {"type": "integer", "required": True, "description": "Index of the cell to edit"},
        "cell_code": {
            "type": "string",
            "required": True,
            "allow_empty": True,
            "description": "New source for the cell (may be empty to clear)",
        },
        "cell_type": {"type": "string", "required": False, "description": "Type: 'code', 'markdown', or 'raw'", "default": "code"}
    },
    returns="string: Success/error message"
)

# Claw-code Tool 8: CommandRunnerTool - Enhanced bash execution

