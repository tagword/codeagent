"""Web UI git endpoints — split out of ``webui_api_app``.

Mounted at ``/api/ui``. This module owns the git/ssh helper cluster (``_run_git``,
``_split_git_args``, ``_git_cwd``, ``_git_credential_*``, ``_ssh_*``,
``_git_host_from_url``, ``_git_provider_host``, ``_git_defaults_path``,
``_git_proxy_path``) as module-level functions plus the git routes via the
``build_git_routes(project_root)`` factory. ``_project_fs_dir`` and
``_default_agent_id`` (defined in ``webui_api_app``) are imported lazily inside
functions to avoid a circular import.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)


def _git_defaults_path(root: Path) -> Path:
    return root / "config" / "codeagent.git.defaults.json"


def _git_proxy_path(root: Path) -> Path:
    return root / "config" / "codeagent.git.proxy.json"


def _git_cwd(body: dict[str, Any], agent_id: str, project_root: Path) -> Path:
    from codeagent.server.webui_api_app import _project_fs_dir

    pid = str(body.get("project_id") or "").strip()
    if pid:
        d = _project_fs_dir(agent_id, pid)
        if d is not None:
            return d
    return project_root


async def _run_git(cwd: Path, argv: list[str]) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return 127, "", "git not found"
    out_b, err_b = await proc.communicate()
    out = out_b.decode("utf-8", errors="replace") if out_b else ""
    err = err_b.decode("utf-8", errors="replace") if err_b else ""
    return int(proc.returncode or 0), out, err


def _split_git_args(args: Any) -> list[str]:
    if isinstance(args, list):
        return [str(x) for x in args]
    s = str(args or "").strip()
    if not s:
        return []
    return shlex.split(s, posix=os.name != "nt")


_GIT_PROVIDER_HTTPS_HOST: dict[str, str] = {
    "github": "github.com",
    "gitlab": "gitlab.com",
    "gitee": "gitee.com",
    "bitbucket": "bitbucket.org",
}

_GIT_PROVIDER_SSH_HOST: dict[str, str] = {
    "github": "git@github.com",
    "gitlab": "git@gitlab.com",
    "gitee": "git@gitee.com",
    "bitbucket": "git@bitbucket.org",
}


def _git_host_from_url(url: str) -> tuple[str, str]:
    raw = (url or "").strip()
    if not raw:
        return "https", ""
    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")
    parsed = urlparse(raw)
    host = (parsed.netloc or parsed.path.split("/")[0] or "").strip().lower()
    scheme = (parsed.scheme or "https").strip().lower()
    return scheme, host


def _git_provider_host(provider: str, *, root: Path | None = None) -> str:
    pid = str(provider or "").strip().lower()
    if not pid and root is not None:
        p = _git_defaults_path(root)
        if p.is_file():
            with contextlib.suppress(Exception):
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    pid = str(data.get("provider") or "").strip().lower()
    return _GIT_PROVIDER_HTTPS_HOST.get(pid, "github.com")


async def _git_credential_pipe(subcmd: str, payload: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        "credential",
        subcmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate(input=(payload + "\n\n").encode("utf-8"))
    out = (out_b or b"").decode(errors="replace").strip()
    err = (err_b or b"").decode(errors="replace").strip()
    return int(proc.returncode or 0), out, err


async def _git_credential_show(root: Path) -> str:
    lines: list[str] = []
    proc = await asyncio.create_subprocess_exec(
        "git",
        "config",
        "--global",
        "--get-regexp",
        r"^credential\.",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    cfg = (out_b or b"").decode(errors="replace").strip()
    if cfg:
        lines.append("credential.helper 配置：")
        lines.extend("  " + ln for ln in cfg.splitlines())
    else:
        lines.append("未设置全局 credential.helper（将使用系统默认，如 osxkeychain）")
    for prov, host in _GIT_PROVIDER_HTTPS_HOST.items():
        rc, fill_out, fill_err = await _git_credential_pipe(
            "fill",
            f"protocol=https\nhost={host}\n",
        )
        if rc == 0 and fill_out.strip():
            lines.append(f"✅ {prov} ({host}): 已配置 HTTPS 凭据")
        elif fill_err:
            lines.append(f"○ {prov} ({host}): 未检测到凭据")
    return "\n".join(lines)


async def _git_credential_store(url: str, username: str, token: str) -> tuple[bool, str]:
    scheme, host = _git_host_from_url(url)
    if not host:
        return False, "无效的 URL / host"
    if not username or not token:
        return False, "用户名和 Token 不能为空"
    payload = f"protocol={scheme}\nhost={host}\nusername={username}\npassword={token}"
    rc, _out, err = await _git_credential_pipe("approve", payload)
    if rc != 0:
        return False, err or "git credential approve 失败"
    return True, f"✅ 已保存 {scheme}://{host} 的 HTTPS 凭据"


async def _git_credential_clear() -> str:
    cleared: list[str] = []
    for host in _GIT_PROVIDER_HTTPS_HOST.values():
        rc, _out, err = await _git_credential_pipe(
            "reject",
            f"protocol=https\nhost={host}\n",
        )
        if rc == 0:
            cleared.append(host)
        elif err and "unknown" not in err.lower():
            logger.debug("credential reject %s: %s", host, err)
    if cleared:
        return "✅ 已清除: " + ", ".join(cleared)
    return "○ 未找到可清除的 HTTPS 凭据（可能未存储或 helper 不支持 reject）"


def _ssh_provider_target(provider: str) -> tuple[str, str]:
    pid = str(provider or "").strip().lower() or "github"
    ssh_host = _GIT_PROVIDER_SSH_HOST.get(pid, "git@github.com")
    return pid, ssh_host


async def _ssh_g_options(ssh_host: str) -> dict[str, list[str]]:
    proc = await asyncio.create_subprocess_exec(
        "ssh",
        "-G",
        ssh_host,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    if proc.returncode != 0:
        logger.debug("ssh -G %s failed: %s", ssh_host, (err_b or b"").decode(errors="replace"))
        return {}
    out: dict[str, list[str]] = {}
    for line in (out_b or b"").decode(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        key, val = parts[0].lower(), parts[1].strip()
        out.setdefault(key, []).append(val)
    return out


async def _ssh_resolve_identities(ssh_host: str) -> list[dict[str, Any]]:
    opts = await _ssh_g_options(ssh_host)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in opts.get("identityfile", []):
        expanded = os.path.expanduser(str(raw).strip())
        if not expanded or expanded in seen:
            continue
        seen.add(expanded)
        priv = Path(expanded)
        pub = priv if priv.suffix == ".pub" else Path(f"{priv}.pub")
        rows.append(
            {
                "private": str(priv),
                "public": str(pub),
                "private_exists": priv.is_file(),
                "public_exists": pub.is_file(),
                "source": "ssh -G",
            }
        )
    return rows


async def _ssh_agent_fingerprints() -> list[str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ssh-add",
            "-l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return []
    out_b, err_b = await proc.communicate()
    if proc.returncode != 0:
        return []
    return [ln.strip() for ln in (out_b or b"").decode(errors="replace").splitlines() if ln.strip()]


async def _ssh_probe(ssh_host: str) -> tuple[bool, str]:
    proc = await asyncio.create_subprocess_exec(
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-T",
        ssh_host,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    text = ((out_b or b"") + (err_b or b"")).decode(errors="replace").strip()
    first = text.split("\n")[0].strip() if text else "无响应"
    ok = "successfully authenticated" in text.lower()
    return ok, first[:200]


async def _ssh_build_status(provider: str, ssh_host: str | None = None) -> dict[str, Any]:
    if not ssh_host:
        pid, ssh_host = _ssh_provider_target(provider)
    else:
        pid = provider or "custom"
    connected, auth_message = await _ssh_probe(ssh_host)
    identities = await _ssh_resolve_identities(ssh_host)
    agent_keys = await _ssh_agent_fingerprints()
    ssh_dir = Path.home() / ".ssh"
    pub_names: list[str] = []
    if ssh_dir.is_dir():
        pub_names = sorted(
            p.name
            for p in ssh_dir.glob("*.pub")
            if not p.name.endswith("-cert.pub")
        )
    effective_pubs = {Path(row["public"]).name for row in identities if row.get("public_exists")}
    if connected:
        recommendation = "ok_no_action"
        recommendation_text = "该平台 SSH 已可用，通常无需再「生成密钥」。"
    elif identities or agent_keys:
        recommendation = "needs_platform_or_config"
        recommendation_text = (
            "本机已有密钥或 agent 条目，但未连通该平台。"
            "请把对应公钥加到 Git 平台，或检查 ~/.ssh/config 的 Host/IdentityFile。"
        )
    else:
        recommendation = "generate_suggested"
        recommendation_text = "未检测到可用密钥，可在此生成默认 id_ed25519，或继续用你现有的 SSH 工具配置。"

    lines: list[str] = []
    if connected:
        lines.append(f"✅ {ssh_host} — {auth_message}")
    else:
        lines.append(f"○ {ssh_host} — {auth_message or '未连通'}")
    lines.append("")
    lines.append("OpenSSH 实际会尝试的密钥（ssh -G，与 git push 一致）：")
    if identities:
        for row in identities:
            mark = "✓" if row["private_exists"] else "✗"
            lines.append(f"  {mark} {row['private']}")
            if row["public_exists"]:
                lines.append(f"      公钥: {row['public']}")
    else:
        lines.append("  （未解析到 identityfile，可能仅依赖 ssh-agent / 系统钥匙串）")
    if agent_keys:
        lines.append("")
        lines.append("ssh-agent 已加载：")
        for ln in agent_keys[:5]:
            lines.append(f"  {ln}")
    other_pubs = [n for n in pub_names if n not in effective_pubs]
    if other_pubs:
        lines.append("")
        lines.append("~/.ssh 内其它公钥（未列入上方优先级）：")
        for nm in other_pubs[:6]:
            lines.append(f"  {nm}")
        if len(other_pubs) > 6:
            lines.append(f"  … 另有 {len(other_pubs) - 6} 个")
    lines.append("")
    lines.append(recommendation_text)
    return {
        "provider": pid,
        "ssh_host": ssh_host,
        "connected": connected,
        "auth_message": auth_message,
        "identities": identities,
        "agent_keys": agent_keys,
        "public_keys_in_ssh_dir": pub_names,
        "recommendation": recommendation,
        "recommendation_text": recommendation_text,
        "result": "\n".join(lines),
    }


async def _ssh_read_public_keys(provider: str) -> tuple[str, str]:
    """Return (text, error). Prefer keys ssh would use for this host."""
    _pid, ssh_host = _ssh_provider_target(provider)
    identities = await _ssh_resolve_identities(ssh_host)
    chunks: list[str] = []
    for row in identities:
        pub = Path(str(row["public"]))
        if pub.is_file():
            try:
                chunks.append(f"# {pub}\n{pub.read_text(encoding='utf-8').strip()}\n")
            except OSError as e:
                return "", str(e)
    if chunks:
        return "\n".join(chunks).strip() + "\n", ""
    agent = await _ssh_agent_fingerprints()
    if agent:
        return "", (
            "当前连接可能仅使用 ssh-agent / 系统钥匙串中的密钥，无法在此导出公钥文本。"
            "请在终端运行: ssh-add -L"
        )
    ssh_dir = Path.home() / ".ssh"
    for nm in ("id_ed25519.pub", "id_rsa.pub"):
        p = ssh_dir / nm
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8"), ""
            except OSError as e:
                return "", str(e)
    pubs = sorted(ssh_dir.glob("*.pub")) if ssh_dir.is_dir() else []
    if len(pubs) == 1:
        try:
            return pubs[0].read_text(encoding="utf-8"), ""
        except OSError as e:
            return "", str(e)
    if pubs:
        names = ", ".join(p.name for p in pubs[:8])
        return "", f"未确定该平台使用哪把钥；~/.ssh 内有: {names}。请配置 ~/.ssh/config 或指定 Host 后再试。"
    return "", "未找到公钥文件；若尚未配置 SSH，可点击「生成密钥」。"



def build_git_routes(project_root: Path) -> list[Route]:
    """Return the git routes for ``webui_api_app``."""

    async def api_git_defaults_get(_: Request) -> JSONResponse:
        p = _git_defaults_path(project_root)
        if not p.is_file():
            return JSONResponse({"defaults": {}})
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        return JSONResponse({"defaults": data if isinstance(data, dict) else {}})

    async def api_git_defaults_put(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"detail": "expected JSON object"}, status_code=400)
        p = _git_defaults_path(project_root)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            return JSONResponse({"detail": str(e)}, status_code=500)
        return JSONResponse({"ok": True})

    async def api_git_proxy_config(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        method = str(body.get("method") or "get")
        path = _git_proxy_path(project_root)
        if method == "get":
            if not path.is_file():
                return JSONResponse({"ok": True, "enabled": False, "http": "", "https": ""})
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            return JSONResponse(
                {
                    "ok": True,
                    "enabled": bool(data.get("enabled")),
                    "http": str(data.get("http") or ""),
                    "https": str(data.get("https") or ""),
                }
            )
        if method == "set":
            path.parent.mkdir(parents=True, exist_ok=True)
            enabled = bool(body.get("enabled"))
            http_val = str(body.get("http") or "").strip()
            https_val = str(body.get("https") or "").strip()
            payload = {
                "enabled": enabled,
                "http": http_val,
                "https": https_val,
            }
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

            # 同步写入 git 全局配置
            async def _proxy_git_set(key: str, val: str) -> None:
                # 先清掉旧的（防止重复值）
                await asyncio.to_thread(
                    subprocess.run,
                    ["git", "config", "--global", "--unset-all", key],
                    capture_output=True, text=True, timeout=10,
                )
                if val:
                    await asyncio.to_thread(
                        subprocess.run,
                        ["git", "config", "--global", key, val],
                        capture_output=True, text=True, timeout=10,
                    )

            for key, val in [("http.proxy", http_val), ("https.proxy", https_val)]:
                if enabled and val:
                    await _proxy_git_set(key, val)
                else:
                    await _proxy_git_set(key, "")  # 仅清除

            return JSONResponse({"ok": True})
        return JSONResponse({"detail": "bad method"}, status_code=400)

    async def api_git_proxy_unset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        scheme = str(body.get("scheme") or "http")
        key = "http" if scheme == "http" else "https"
        path = _git_proxy_path(project_root)
        data: dict[str, Any] = {}
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data = raw
            except (json.JSONDecodeError, OSError):
                pass
        data[key] = ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        arg = "http.proxy" if scheme == "http" else "https.proxy"
        await asyncio.to_thread(
            subprocess.run,
            ["git", "config", "--global", "--unset-all", arg],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return JSONResponse({"ok": True})

    async def api_git_post(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import (
            _default_agent_id,
        )
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        cmd = str(body.get("command") or "").strip()
        args = body.get("args", "")
        aid = _default_agent_id()
        cwd = _git_cwd(body, aid, project_root)

        if cmd == "remote":
            extra = _split_git_args(args)
            if not extra:
                rc, out, err = await _run_git(cwd, ["remote", "-v"])
                if rc != 0:
                    return JSONResponse({"result": "未配置远程仓库（git remote 不可用）\n" + err})
                return JSONResponse({"result": out or err})
            rc, out, err = await _run_git(cwd, ["remote", *extra])
            text = (out or "") + (err or "")
            return JSONResponse({"result": text, "error": err if rc != 0 else ""})

        if cmd == "test-remote":
            name = str(args or "").strip()
            rc, out, err = await _run_git(cwd, ["ls-remote", "--heads", name])
            return JSONResponse({"result": out or err, "error": err if rc != 0 else ""})

        if cmd == "ssh":
            arg = str(args or "").strip()
            provider = str(body.get("provider") or "").strip().lower()
            ssh_host = str(body.get("host") or "").strip() or None
            force_generate = bool(body.get("force"))
            if arg == "status":
                status = await _ssh_build_status(provider, ssh_host=ssh_host)
                return JSONResponse(status)
            if arg == "cat":
                text, err = await _ssh_read_public_keys(provider)
                if err:
                    return JSONResponse({"result": "", "error": err})
                return JSONResponse({"result": text})
            if arg == "generate":
                st = await _ssh_build_status(provider, ssh_host=ssh_host)
                if st.get("connected") and not force_generate:
                    return JSONResponse(
                        {
                            "result": (
                                "当前平台 SSH 已可用，通常无需生成新密钥。\n"
                                "若仍要创建 ~/.ssh/id_ed25519，请再次确认。"
                            ),
                            "needs_confirm": True,
                            "recommendation": st.get("recommendation"),
                        }
                    )
                ssh_dir = Path.home() / ".ssh"
                ssh_dir.mkdir(parents=True, exist_ok=True)
                key_path = ssh_dir / "id_ed25519"
                if key_path.is_file():
                    pub = ssh_dir / "id_ed25519.pub"
                    hint = pub.read_text(encoding="utf-8") if pub.is_file() else ""
                    return JSONResponse(
                        {"result": "已有 ~/.ssh/id_ed25519。\n" + (hint or ""), "already_exists": True}
                    )
                proc = await asyncio.create_subprocess_exec(
                    "ssh-keygen",
                    "-t",
                    "ed25519",
                    "-f",
                    str(key_path),
                    "-N",
                    "",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                out_b, err_b = await proc.communicate()
                text = (out_b or b"").decode() + (err_b or b"").decode()
                pub = ssh_dir / "id_ed25519.pub"
                if pub.is_file():
                    text = (text.strip() + "\n\n" + pub.read_text(encoding="utf-8")).strip()
                return JSONResponse({"result": text.strip() or "完成"})
            if arg == "test":
                if ssh_host:
                    _pid, _ssh_host = provider, ssh_host
                else:
                    _pid, _ssh_host = _ssh_provider_target(provider)
                ok, first = await _ssh_probe(_ssh_host)
                label = _pid or "github"
                prefix = "✅" if ok else "○"
                return JSONResponse({"result": f"[{label} → {ssh_host}]\n{prefix} {first}"})

        if cmd == "credential":
            action = str(body.get("action") or "").strip().lower()
            if not action and args:
                action = str(args).split()[0].strip().lower()
            if action == "store":
                url = str(body.get("url") or "").strip()
                user = str(body.get("username") or "").strip()
                token = str(body.get("token") or "").strip()
                ok, msg = await _git_credential_store(url, user, token)
                if not ok:
                    return JSONResponse({"error": msg})
                return JSONResponse({"result": msg})
            if action == "show":
                text = await _git_credential_show(project_root)
                return JSONResponse({"result": text})
            if action == "fill":
                # 按 host 精确检查该主机是否有已存凭据（供前端方案卡片 PAT 状态显示）
                target = str(body.get("host") or "").strip()
                if not target:
                    return JSONResponse({"error": "缺少 host"}, status_code=400)
                scheme, host = _git_host_from_url(target)
                if not host:
                    return JSONResponse({"error": f"无效的 host: {target}"}, status_code=400)
                rc, out, err = await _git_credential_pipe(
                    "fill",
                    f"protocol={scheme}\nhost={host}\n",
                )
                if rc == 0 and "password=" in out:
                    return JSONResponse({"has_credential": True, "host": host})
                return JSONResponse({"has_credential": False, "host": host})
            if action == "clear":
                text = await _git_credential_clear()
                return JSONResponse({"result": text})
            return JSONResponse({"detail": "credential action: store|show|clear"}, status_code=400)

        # ---- 核心 git 命令：log / diff / status / commit / branch / push / pull ----
        if cmd == "log":
            extra = _split_git_args(args)
            rc, out, err = await _run_git(cwd, ["log", *extra])
            if rc != 0:
                return JSONResponse({"result": out, "error": err.strip() or "git log 失败"})
            return JSONResponse({"result": out})

        if cmd == "diff":
            extra = _split_git_args(args)
            rc, out, err = await _run_git(cwd, ["diff", *extra])
            return JSONResponse({"result": out or err, "error": err if rc != 0 else ""})

        if cmd == "status":
            rc, out, err = await _run_git(cwd, ["status"])
            return JSONResponse({"result": out or err, "error": err if rc != 0 else ""})

        if cmd == "commit":
            msg = str(body.get("message") or "").strip()
            if not msg:
                return JSONResponse({"error": "提交信息不能为空"}, status_code=400)
            # 先 add -A，再 commit
            rc1, out1, err1 = await _run_git(cwd, ["add", "-A"])
            if rc1 != 0:
                return JSONResponse({"result": out1, "error": err1.strip() or "git add 失败"})
            rc2, out2, err2 = await _run_git(cwd, ["commit", "-m", msg])
            if rc2 != 0:
                return JSONResponse({"result": out2, "error": err2.strip() or "git commit 失败"})
            return JSONResponse({"result": (out2 or err2).strip() or "提交成功"})

        if cmd == "branch":
            extra = _split_git_args(args)
            rc, out, err = await _run_git(cwd, ["branch", *extra])
            return JSONResponse({"result": out or err, "error": err if rc != 0 else ""})

        if cmd == "push":
            extra = _split_git_args(args)
            rc, out, err = await _run_git(cwd, ["push", *extra])
            return JSONResponse({"result": (out or err).strip(), "error": err if rc != 0 else ""})

        if cmd == "pull":
            extra = _split_git_args(args)
            rc, out, err = await _run_git(cwd, ["pull", *extra])
            return JSONResponse({"result": (out or err).strip(), "error": err if rc != 0 else ""})

        return JSONResponse({"detail": "unsupported git command"}, status_code=400)



    return [
        Route("/git/defaults", api_git_defaults_get, methods=["GET"]),
        Route("/git/defaults", api_git_defaults_put, methods=["PUT"]),
        Route("/git/proxy-config", api_git_proxy_config, methods=["POST"]),
        Route("/git/proxy", api_git_proxy_unset, methods=["POST"]),
        Route("/git", api_git_post, methods=["POST"]),
    ]
