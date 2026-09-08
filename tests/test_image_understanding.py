"""codeagent.core.image_understanding 单元测试。

覆盖 image_attachment_allowed / video_attachment_allowed 的分支逻辑：
MCP sentinel、空 vision id、vision preset 支持判断。外部依赖 monkeypatch 隔离。
"""
import pytest

from codeagent.core import image_understanding as iu


# ---------- image_attachment_allowed ----------
def test_image_allowed_mcp_sentinel_configured(monkeypatch):
    monkeypatch.setattr(iu, "minimax_mcp_configured", lambda base=None: True)
    assert iu.image_attachment_allowed(iu.MCP_VISION_SENTINEL) is True


def test_image_allowed_mcp_sentinel_not_configured(monkeypatch):
    monkeypatch.setattr(iu, "minimax_mcp_configured", lambda base=None: False)
    assert iu.image_attachment_allowed(iu.MCP_VISION_SENTINEL) is False


def test_image_allowed_vision_preset(monkeypatch):
    monkeypatch.setattr(
        "codeagent.core.vision_models.preset_supports_vision_id", lambda vid: vid == "vision-model"
    )
    assert iu.image_attachment_allowed("vision-model") is True
    assert iu.image_attachment_allowed("non-vision-model") is False


def test_image_allowed_empty_uses_mcp_fallback(monkeypatch):
    # 空 vision id → 回退到 MCP 是否配置
    monkeypatch.setattr(iu, "minimax_mcp_configured", lambda base=None: True)
    assert iu.image_attachment_allowed("") is True
    monkeypatch.setattr(iu, "minimax_mcp_configured", lambda base=None: False)
    assert iu.image_attachment_allowed(None) is False


# ---------- video_attachment_allowed ----------
def test_video_allowed_requires_vision_preset(monkeypatch):
    monkeypatch.setattr(
        "codeagent.core.vision_models.preset_supports_vision_id", lambda vid: vid == "vision-model"
    )
    assert iu.video_attachment_allowed("vision-model") is True
    assert iu.video_attachment_allowed("non-vision") is False


def test_video_allowed_empty_false():
    assert iu.video_attachment_allowed("") is False
    assert iu.video_attachment_allowed(None) is False


def test_video_does_not_accept_mcp_sentinel(monkeypatch):
    # 视频分析只认 vision preset，不接受 MCP sentinel（与图像不同）
    monkeypatch.setattr(
        "codeagent.core.vision_models.preset_supports_vision_id", lambda vid: False
    )
    assert iu.video_attachment_allowed(iu.MCP_VISION_SENTINEL) is False


# ---------- minimax_mcp_understand_image_ready ----------
def test_ready_false_when_not_configured(monkeypatch):
    monkeypatch.setattr(iu, "minimax_mcp_configured", lambda base=None: False)
    assert iu.minimax_mcp_understand_image_ready() is False


def test_ready_true_when_configured_no_probe(monkeypatch):
    monkeypatch.setattr(iu, "minimax_mcp_configured", lambda base=None: True)
    assert iu.minimax_mcp_understand_image_ready() is True


def test_ready_probe_connected_with_tool(monkeypatch):
    monkeypatch.setattr(iu, "minimax_mcp_configured", lambda base=None: True)
    rows = [{"id": iu.MINIMAX_MCP_SERVER_ID, "connected": True, "tools": ["understand_image", "web_search"]}]
    assert iu.minimax_mcp_understand_image_ready(probe=True, servers_status=rows) is True


def test_ready_probe_no_tool(monkeypatch):
    monkeypatch.setattr(iu, "minimax_mcp_configured", lambda base=None: True)
    rows = [{"id": iu.MINIMAX_MCP_SERVER_ID, "connected": True, "tools": ["web_search"]}]
    assert iu.minimax_mcp_understand_image_ready(probe=True, servers_status=rows) is False


def test_ready_probe_disconnected(monkeypatch):
    monkeypatch.setattr(iu, "minimax_mcp_configured", lambda base=None: True)
    rows = [{"id": iu.MINIMAX_MCP_SERVER_ID, "connected": False, "tools": ["understand_image"]}]
    assert iu.minimax_mcp_understand_image_ready(probe=True, servers_status=rows) is False


def test_ready_probe_ignores_other_servers(monkeypatch):
    monkeypatch.setattr(iu, "minimax_mcp_configured", lambda base=None: True)
    rows = [{"id": "other-server", "connected": True, "tools": ["understand_image"]}]
    assert iu.minimax_mcp_understand_image_ready(probe=True, servers_status=rows) is False


# ---------- image_understanding_status ----------
def test_status_structure(monkeypatch):
    monkeypatch.setattr(iu, "minimax_mcp_configured", lambda base=None: True)
    monkeypatch.setattr(iu, "minimax_mcp_understand_image_ready", lambda base=None, probe=False, servers_status=None: True)
    s = iu.image_understanding_status()
    assert s["configured"] is True
    assert s["ready"] is True
    assert s["sentinel"] == iu.MCP_VISION_SENTINEL
    assert "mcp_tool" in s and "minimax_server_id" in s
