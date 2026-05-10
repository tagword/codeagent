"""Tool execution framework for CodeAgent"""
import logging
import re


logger = logging.getLogger(__name__)


# Harmless Windows disassembler/telemetry lines leak into stderr on some hosts, e.g.
#   `[0x7FFD5CC07FC4] ANOMALY: use of REX.w is meaningless (default operand size is 64)`
# They confuse the model into thinking the command failed. Filter them out of
# tool output so only real stdout/stderr survives.
_ANOMALY_LINE_RE = re.compile(
    r"\[0x[0-9A-Fa-f]+\]\s+ANOMALY:[^\r\n]*(?:\r?\n)?",
)



