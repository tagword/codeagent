"""Memory System for CodeAgent - Manages identity, soul, experiences, and capabilities"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MemorySystemError(Exception):
    """Exception raised for memory system errors"""
    
    def __init__(self, operation: str, path: str, error: str):
        self.operation = operation
        self.path = path
        self.error = error
        super().__init__(f"Memory {operation} error at '{path}': {error}")





import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


logger = logging.getLogger(__name__)


class MemorySystem:
    """
    Manages agent memory including identity, values, experiences, and capabilities.
    Loads automatically when Agent starts with --session flag.
    """
    
    # Track the absolute path to the memory system source file for path resolution
    _source_path = Path(__file__).resolve()
    
    def __init__(self, base_path: Optional[Union[str, Path]] = None, auto_load: bool = False):
        """
        Initialize the memory system.
        
        Args:
            base_path: Base directory for memory storage. 
                       If path contains 'memory', use it directly as memory_path.
                       Otherwise, base_path/config and base_path/memory.
            auto_load: If True, automatically load memory components on init.
        """
        if base_path is None:
            # Default to project root config and memory directories
            base_path = self._source_path.parent.parent
        elif isinstance(base_path, str):
            base_path = Path(base_path)
        
        # Resolve relative paths relative to source file location, not CWD
        if not base_path.is_absolute():
            base_path = (self._source_path.parent.parent / base_path).resolve()
        
        # Normalize path handling to avoid duplication
        # Check if base_path already IS the memory directory (ends with "memory")
        if base_path.name == 'memory':
            # User passed memory directory directly as base_path
            # Use it as memory_path and set base_path to parent
            self.memory_path = base_path
            self.base_path = base_path.parent if base_path.parent else base_path
            self.config_path = self.base_path / "config" if not base_path.name == 'memory' else base_path / "config"
            self.capabilities_path = self.base_path / "capabilities.md"
        else:
            # Normal case: base_path is project root or config directory
            self.base_path: Path = base_path
            self.memory_path = self.base_path / "memory"
            self.config_path = self.base_path / "config"
            self.capabilities_path = self.base_path / "capabilities.md"
        
        # FIX: If memory_path ends with "memory/memory", correct it
        if str(self.memory_path).endswith('/memory/memory') or (self.memory_path.name == 'memory' and self.memory_path.parent.name == 'memory'):
            # This would be memory/memory - use the inner memory
            self.memory_path = (self.base_path / "memory").resolve()
        
        # Paths already resolved above, but ensure they're absolute
        if not self.base_path.is_absolute():
            self.base_path = (self._source_path.parent.parent / self.base_path).resolve()
        if not self.memory_path.is_absolute():
            self.memory_path = (self._source_path.parent.parent / self.memory_path).resolve()
        if not self.config_path.is_absolute():
            self.config_path = (self._source_path.parent.parent / self.config_path).resolve()
        if not self.capabilities_path.is_absolute():
            self.capabilities_path = (self._source_path.parent.parent / self.capabilities_path).resolve()
        
        # Ensure directories exist
        self._ensure_directories()
        
        # In-memory cache
        self.identity_cache: Optional[Dict[str, str]] = None
        self.soul_cache: Optional[Dict[str, str]] = None
        self.capabilities: Dict[str, Dict[str, Any]] = {}
        self._experiences: List[Dict[str, Any]] = []

        # Auto-load on initialization if requested (for backward compatibility with tests)
        if auto_load:
            try:
                self.load_all()
            except Exception:
                logger.warning("Auto-load of MemorySystem failed during initialization.")
    
    def _ensure_directories(self) -> None:
        """Create required directories if they don't exist"""
        try:
            self.config_path.mkdir(parents=True, exist_ok=True)
            self.memory_path.mkdir(parents=True, exist_ok=True)
            
            # Create memory subdirectories
            (self.memory_path / "learning").mkdir(exist_ok=True)
            (self.memory_path / "skills").mkdir(exist_ok=True)
            (self.memory_path / "patterns").mkdir(exist_ok=True)
            (self.memory_path / "experiences").mkdir(exist_ok=True)
            
            logger.debug(f"Memory directories ensured: {self.memory_path}")
        except OSError as e:
            raise MemorySystemError("create", str(self.memory_path), str(e))
    
    # ==========================================================================
    # Identity Management (config/identity.md)
    # ==========================================================================
    
    def load_identity(self) -> Dict[str, str]:
        """
        Load agent identity from config/identity.md.
        
        Returns:
            Dictionary of identity sections and their content
        """
        identity_file = self.config_path / "identity.md"
        
        if not identity_file.exists():
            logger.warning(f"Identity file not found: {identity_file}")
            return self._create_default_identity(identity_file)
        
        try:
            with open(identity_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            identity_dict = self._parse_markdown_to_dict(content)
            self.identity_cache = identity_dict
            logger.info(f"Identity loaded from {identity_file}")
            return identity_dict
        except OSError as e:
            raise MemorySystemError("load", str(identity_file), str(e))
    
    def save_identity(self, identity_data: Dict[str, str]) -> None:
        """
        Save agent identity to config/identity.md.
        
        Args:
            identity_data: Dictionary of identity sections
        """
        identity_file = self.config_path / "identity.md"
        
        try:
            content = self._dict_to_markdown(identity_data)
            with open(identity_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.identity_cache = identity_data
            logger.info(f"Identity saved to {identity_file}")
        except OSError as e:
            raise MemorySystemError("save", str(identity_file), str(e))
    
    def _create_default_identity(self, file_path: Path) -> Dict[str, str]:
        """Create default identity file if it doesn't exist"""
        default_identity = {
            "Self-Concept": "I am an autonomous AI agent designed to learn, grow, and adapt through experience.",
            "Capabilities": "- Tool usage and discovery\n- Task execution and planning\n- Self-reflection and memory management",
            "Learning Goals": "- Improve tool composition skills\n- Develop strategic decision-making\n- Build efficiency heuristics",
            "Current State": "- Session: Active\n- Memory: Persistent (file-based)\n- Tools Available: echo, calculate, counter, whoami"
        }
        
        content = self._dict_to_markdown(default_identity)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Default identity created: {file_path}")
        except OSError as e:
            raise MemorySystemError("create", str(file_path), str(e))
        
        return default_identity
    
    # ==========================================================================
    # Soul/Values Management (config/soul.md)
    # ==========================================================================
    
    def load_soul(self) -> Dict[str, str]:
        """
        Load agent values and ethics from config/soul.md.
        
        Returns:
            Dictionary of soul sections and their content
        """
        soul_file = self.config_path / "soul.md"
        
        if not soul_file.exists():
            logger.warning(f"Soul file not found: {soul_file}")
            return self._create_default_soul(soul_file)
        
        try:
            with open(soul_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            soul_dict = self._parse_markdown_to_dict(content)
            self.soul_cache = soul_dict
            logger.info(f"Soul/values loaded from {soul_file}")
            return soul_dict
        except OSError as e:
            raise MemorySystemError("load", str(soul_file), str(e))
    


import logging
logger = logging.getLogger(__name__)

def _get_level_by_rank(self, rank: int) -> str:
    """Get the level name by numeric rank."""
    level_order = [
        "novice",
        "learning",
        "skilled",
        "competent",
        "proficient",
        "expert",
        "master"
    ]
    return level_order[rank] if 0 <= rank < len(level_order) else "novice"

def _get_auto_upgrade_level(self, total_usage: int) -> str:
    """Determine auto-upgraded level based on total usage count."""
    if total_usage >= 10:
        return "master"
    elif total_usage >= 7:
        return "expert"
    elif total_usage >= 5:
        return "proficient"
    elif total_usage >= 3:
        return "competent"
    elif total_usage >= 2:
        return "skilled"
    else:
        return "learning"

# ==========================================================================
# Capability Tracking (capabilities.md)
# ==========================================================================

def track_capability(self, capability: str, level: str) -> None:
    """
    Track agent capability level in capabilities.md.
    
    Args:
        capability: Name of the capability (e.g., 'task_planning', 'tool_discovery')
        level: Proficiency level (novice, competent, proficient, master)
    """
    # Load current capabilities with total_usage tracking
    capabilities = self.load_capabilities()
    
    # Increment total_usage for this capability (or initialize to 1 if new)
    if capability in capabilities:
        capabilities[capability]["total_usage"] = capabilities[capability].get("total_usage", 0) + 1
    else:
        capabilities[capability] = {"level": level, "total_usage": 1}
    
    # Auto-advance level based on total_usage if the provided level is lower than what usage suggests
    current_usage = capabilities[capability]["total_usage"]
    auto_level = self._get_auto_upgrade_level(current_usage)
    
    # Get the expected level for the provided level string
    provided_level_rank = self._get_level_rank(level)
    auto_level_rank = self._get_level_rank(auto_level)
    
    # Use the higher level (either the explicitly provided level or auto-upgraded level)
    if auto_level_rank > provided_level_rank:
        level = auto_level
        logger.debug(f"Auto-upgraded {capability} from {self._get_level_by_rank(provided_level_rank)} to {auto_level} based on usage count {current_usage}")
    
    # Update the level
    capabilities[capability]["level"] = level
    
    # Save using save_capabilities which writes the full data structure
    self.save_capabilities(capabilities)
    
    logger.info(f"Capability tracked: {capability} -> {level} (usage: {capabilities[capability]['total_usage']})")

def _update_capability_status(
    self, 
    content: str, 
    capability: str, 
    level: str
) -> str:
    """
    Update capability status in markdown content.
    
    Args:
        content: Current markdown content
        capability: Capability name
        level: New proficiency level
    
    Returns:
        Updated markdown content
    """
    import re
    
    # Map proficiency levels to checkboxes
    level_map = {
        "master": "[x]",
        "proficient": "[x]✓",
        "expert": "[x]",
        "competent": "[x]~",
        "learning": "[/]",  # In-progress: [/]
        "skilled": "[~]",   # Intermediate: [~]
        "novice": "[ ]"
    }
    
    level_symbol = level_map.get(level.lower(), "[ ]")
    capability_display = capability
    
    # Check if capabilities.md exists and has content
    if not self.capabilities_path.exists() or not content.strip():
        # Create new capabilities file with the capability
        content = f"# Agent Capabilities & Tool Proficiency\n\n## Active Capabilities\n\n- {level_symbol} {capability_display}\n"
        return content
    
    # Convert to lower case for matching
    capability_lower = capability.lower()
    
    # Find and update the capability line
    # Pattern: - [ ] capability_name or - [x] capability_name or - [/] capability_name or - [~]
    # Must match the exact checkbox format from load_capabilities
    pattern = r'^- \[(x|/|~|\s+)\]([~✓]?)\s*' + re.escape(capability_lower) + r'\s*$'
    
    if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
        # Update existing capability - replace entire line with properly formatted one
        content = re.sub(
            pattern,
            f'- {level_symbol} {capability_lower}',
            content,
            flags=re.IGNORECASE | re.MULTILINE,
            count=1
        )
    else:
        # Add new capability to the list
        # Look for "## Active Capabilities" or "Active:" section
        insert_patterns = [
            r'(## Active Capabilities\s*\n)',
            r'(## Capability Tags\s*\*\*Active:\*\*)',
            r'(Active Capabilities\s*\n- \[-\])'
        ]
        
        added = False
        for pattern in insert_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                new_line = f"\n- {level_symbol} {capability_display.lower()}"
                # FIX: Prepend newline to captured group to ensure new list item
                content = re.sub(pattern, new_line, content, flags=re.IGNORECASE, count=1)
                added = True
                break
        
        # If we couldn't find a section, add at the end of Active section
        if not added:
            # Find the first list item and add after it
            list_pattern = r'(- \[\s*x\s*\]\s+.+)'
            match = re.search(list_pattern, content, re.IGNORECASE)
            if match:
                insert_pos = match.end()
                content = content[:insert_pos] + f"\n- {level_symbol} {capability_display.lower()}" + content[insert_pos:]
            else:
                # Just append to the file
                content += f"\n- {level_symbol} {capability_display.lower()}\n"
    
    return content

# ==========================================================================
# Capability Management Methods
# ==========================================================================



from typing import List, Dict, Any

def is_memory_empty(self) -> bool:
    """
    Check if memory system has any loaded data.
    
    Returns:
        True if memory is empty (no identity, soul, capabilities, or experiences),
        False if any memory components are loaded
    """
    # Check identity - if load_identity() returns empty dict, memory is empty
    identity = self.load_identity()
    # Identity may exist without agent_name; treat as valid if any content exists
    if not identity:
        # Check if fast path cache exists (experiences are stored there)
        fast_path_dir = self._get_fast_path_path()
        if fast_path_dir.exists() and any(fast_path_dir.glob("*.md")):
            return False
        return True
    
    # Check capabilities
    if not self.capabilities:
        return True
    
    # Check experiences
    if not self._experiences:
        # Still check fast path cache
        fast_path_dir = self._get_fast_path_path()
        if fast_path_dir.exists() and any(fast_path_dir.glob("*.md")):
            return False
        return True
    
    return False

def get_all_experiences(self) -> List[Dict[str, Any]]:
    """
    Get all loaded experiences.
    
    Returns:
        List of experience dictionaries
    """
    return self._experiences

def summarize_memory(self) -> Dict[str, Any]:
    """
    Generate a memory summary for session logging.
    
    Returns:
        Dictionary with memory summary data
    """
    identity = self.identity_cache or self.load_identity()
    soul = self.soul_cache or self.load_soul()
    
    # Count files in each memory category
    categories = {
        "learning": (self.memory_path / "learning").glob("*.md"),
        "skills": (self.memory_path / "skills").glob("*.md"),
        "patterns": (self.memory_path / "patterns").glob("*.md"),
        "experiences": (self.memory_path / "experiences").glob("*.md")
    }
    
    counts = {}
    for category, pattern in categories.items():
        counts[category] = len(list(pattern))
    
    return {
        "identity_sections": len(identity),
        "soul_sections": len(soul),
        "memory_categories": counts,
        "capabilities_path": str(self.capabilities_path) if self.capabilities_path.exists() else ""
    }

def analyze_experiences(self) -> Dict[str, Any]:
    """
    Analyze all logged experiences to identify patterns and suggest improvements.
    
    Returns:
        Analysis results with success rate, common failures, and recommendations
    """
    experience_files = list((self.memory_path / "experiences").glob("*.md"))
    
    if not experience_files:
        return {
            "total_experiences": 0,
            "success_rate": 0,
            "common_patterns": [],
            "improvement_areas": []
        }
    
    successful = 0
    failed = 0
    tool_success_rates = {}
    tool_counts = {}
    
    for exp_file in experience_files:
        try:
            with open(exp_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Parse outcome from YAML-like format: `## Outcome:\noutcome: success`
                # or check for Success/Completed in Outcome field
                outcome_line_idx = None
                for i, line in enumerate(content.split('\n')):
                    if '## outcome' in line.lower():
                        outcome_line_idx = i
                        break
                
                # Count based on outcome field value
                if outcome_line_idx is not None:
                    all_lines = content.split('\n')
                    # Look at the line after "## Outcome" (and any non-blank lines after it)
                    outcome_content = []
                    for j in range(outcome_line_idx + 1, len(all_lines)):
                        line = all_lines[j].strip()
                        if line:
                            outcome_content.append(line)
                    outcome_lower = ' '.join(outcome_content).lower()
                    
                    # Success indicators: "completed", "success" in outcome section
                    if 'completed' in outcome_lower or 'success' in outcome_lower:
                        successful += 1
                    else:
                        failed += 1
                else:
                    # Fallback: look for success indicators
                    if "success: true" in content.lower() or "outcome: success" in content.lower() or "status: completed" in content.lower():
                        successful += 1
                    else:
                        failed += 1
                
                # Don't try to extract tool from filename (it's timestamp-based)
                # Tool association comes from capabilities, not experience files
        except Exception:
            continue
    
    total = successful + failed
    success_rate = (successful / total * 100) if total > 0 else 0
    
    # Calculate tool-specific success rates from capabilities
    capabilities = self.load_capabilities()
    for capability, data in capabilities.items():
        if data.get("level") in ["competent", "proficient", "master"]:
            tool_success_rates[capability] = data.get("level")
    
    # Generate improvement suggestions
    suggestions = []
    if success_rate < 50:
        suggestions.append("High failure rate detected. Review recent failed tasks and consider simplifying task approach.")
    
    # Identify tools needing improvement
    for tool, level in tool_success_rates.items():
        if level == "novice":
            suggestions.append(f"Consider practicing '{tool}' tool to improve proficiency from {level} to competent.")
    
    return {
        "total_experiences": total,
        "successful": successful,
        "failed": failed,
        "success_rate": round(success_rate, 1),
        "tool_usage_count": tool_counts,
        "improvement_areas": suggestions
    }

