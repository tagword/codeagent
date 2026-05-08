"""Shell command execution helpers"""
import os
import subprocess
import sys
import logging
logger = logging.getLogger(__name__)


def _run_shell_command(command, timeout=30, cwd=None, detach=False):
    """Execute a shell command and return (returncode, stdout, stderr)."""
    
    if detach:
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            if sys.version_info >= (3, 7):
                kwargs["creationflags"] |= subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(
            command if os.name != "nt" else ["cmd.exe", "/c", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs
        )
        return (0, f"Detached PID: {proc.pid}", "")
    
    try:
        result = subprocess.run(
            command if os.name != "nt" else ["cmd.exe", "/c", command],
            capture_output=True, text=True, timeout=timeout,
            cwd=cwd
        )
        return (result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (-1, "", "Command timed out")
    except Exception as e:
        return (-1, "", str(e))


def _format_shell_output(returncode, stdout, stderr, max_output=100000):
    """Format shell output for the model."""
    output_parts = []
    
    if stderr:
        from seed.tools.shell_helpers import _filter_shell_noise
        cleaned_stderr = _filter_shell_noise(stderr)
        if cleaned_stderr:
            output_parts.append(f"STDERR:\n{cleaned_stderr[:2000]}")
    
    if stdout:
        if len(stdout) > max_output:
            output_parts.append(f"STDOUT (truncated, {len(stdout)} bytes):\n{stdout[:max_output]}")
            output_parts.append(f"... (truncated {len(stdout) - max_output} bytes)")
        else:
            output_parts.append(f"STDOUT:\n{stdout}")
    
    return "\n".join(output_parts)
