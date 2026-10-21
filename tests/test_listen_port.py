"""codeagent.server._request_listen_port 单元测试。

覆盖端口解析：URL port / Host header（含 IPv6）/ env fallback。
"""
from codeagent.server import _request_listen_port


class FakeURL:
    def __init__(self, port):
        self.port = port


class FakeRequest:
    def __init__(self, url_port=None, host=None):
        self.url = FakeURL(url_port)
        self.headers = {"host": host} if host else {}


def _clear(monkeypatch):
    monkeypatch.delenv("CODEAGENT_PORT", raising=False)


# ---------- URL port 优先 ----------
def test_uses_url_port(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_PORT", "9999")
    assert _request_listen_port(FakeRequest(url_port=8080)) == 8080


def test_url_port_none_falls_back(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_PORT", "8765")
    assert _request_listen_port(FakeRequest(url_port=None)) == 8765


# ---------- Host header ----------
def test_host_with_port(monkeypatch):
    _clear(monkeypatch)
    assert _request_listen_port(FakeRequest(host="example.com:3000")) == 3000


def test_host_without_port_uses_env(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_PORT", "4321")
    assert _request_listen_port(FakeRequest(host="example.com")) == 4321


def test_ipv6_host_with_port(monkeypatch):
    _clear(monkeypatch)
    assert _request_listen_port(FakeRequest(host="[::1]:8765")) == 8765


def test_ipv6_host_without_port_uses_env(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_PORT", "7000")
    assert _request_listen_port(FakeRequest(host="[2001:db8::1]")) == 7000


def test_host_non_numeric_port_uses_env(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_PORT", "5555")
    assert _request_listen_port(FakeRequest(host="example.com:abc")) == 5555


# ---------- env fallback ----------
def test_env_invalid_port_uses_default(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_PORT", "not-a-port")
    assert _request_listen_port(FakeRequest()) == 8765


def test_no_env_uses_default(monkeypatch):
    _clear(monkeypatch)
    assert _request_listen_port(FakeRequest()) == 8765
