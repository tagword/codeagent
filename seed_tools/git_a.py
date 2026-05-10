"""Git tool"""
import os
import subprocess
import logging
logger = logging.getLogger(__name__)

def git_tool_handler(command: str, args: str = "", message: str = "") -> str:
    """
    统一的 git 操作工具。支持 init / status / diff / commit / log / branch / push / pull。
    
    Args:
        command: 子命令: status, diff, commit, log, branch, push, pull, init, add
        args: 子命令的额外参数（如 branch 名、log 选项等）
        message: commit message（commit 时使用）
    
    Returns:
        git 命令输出
    """

    cwd = os.getcwd()

    def _run(git_args: list, cwd_dir: str = "") -> str:
        """Run git command and return output."""
        wd = cwd_dir or cwd
        try:
            result = subprocess.run(
                ["git"] + git_args,
                capture_output=True, text=True, timeout=30,
                cwd=wd,
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            if result.returncode != 0:
                return f"❌ git 错误 (exit {result.returncode}):\n{stderr[:1000]}"
            out = stdout
            if stderr:
                out = out + "\n" + stderr[:500] if out else stderr[:500]
            return out or "(无输出)"
        except FileNotFoundError:
            return "❌ git 未安装，请先安装 git"
        except subprocess.TimeoutExpired:
            return "❌ git 命令超时（30s）"
        except Exception as e:
            return f"❌ git 执行失败: {e}"

    cmd = command.strip().lower()

    # --- init ---
    if cmd == "init":
        out = _run(["init"])
        if "已初始化空的 Git 仓库" in out or "Initialized empty Git repository" in out:
            # 建议设置 user config
            name_check = _run(["config", "user.name"])
            email_check = _run(["config", "user.email"])
            hints = []
            if "fatal" in name_check.lower() or not name_check.strip():
                hints.append("💡 提示: 设置 git config user.name 和 user.email")
            return out + ("\n" + "\n".join(hints) if hints else "")
        return out

    # --- status ---
    if cmd == "status":
        raw = _run(["status", "--porcelain"])
        branch_out = _run(["branch", "--show-current"])
        if raw == "(无输出)":
            return f"🌿 当前分支: {branch_out}\n\n✅ 工作区干净，无改动"
        lines = [l for l in raw.split("\n") if l.strip()]
        staged = [l for l in lines if l[0] != "?" and l[0] != " "]
        unstaged = [l for l in lines if l[0] == " "]
        untracked = [l for l in lines if l[0] == "?"]
        output = f"🌿 当前分支: {branch_out}\n\n"
        if staged:
            output += f"📌 已暂存 ({len(staged)}):\n" + "\n".join(f"   {l}" for l in staged) + "\n\n"
        if unstaged:
            output += f"📝 未暂存 ({len(unstaged)}):\n" + "\n".join(f"   {l}" for l in unstaged) + "\n\n"
        if untracked:
            output += f"🆕 未跟踪 ({len(untracked)}):\n" + "\n".join(f"   {l}" for l in untracked) + "\n\n"
        if not lines:
            output += "✅ 工作区干净，无改动"
        return output.strip()

    # --- diff ---
    if cmd == "diff":
        diff_args = ["diff"]
        if args:
            diff_args.append(args)
        out = _run(diff_args)
        if not out or out == "(无输出)":
            # 试试 staged diff
            staged_out = _run(["diff", "--cached"])
            if staged_out and staged_out != "(无输出)":
                return f"📋 暂存区变更 (diff --cached):\n\n{staged_out}"
            return "✅ 无未提交的变更"
        return f"📋 变更内容:\n\n{out[:3000]}" + ("\n...(截断)" if len(out) > 3000 else "")

    # --- commit ---
    if cmd == "commit":
        if not message:
            return "❌ commit 需要提供 message 参数"
        # 自动 add 所有变更
        add_out = _run(["add", "-A"])
        if add_out.startswith("❌"):
            return f"git add 失败:\n{add_out}"
        # commit
        commit_out = _run(["commit", "-m", message])
        # 检查是否真的提交了
        if "nothing to commit" in commit_out.lower() or "nothing added" in commit_out.lower():
            return "✅ 无变更需要提交"
        if "changed" in commit_out.lower() or "insertion" in commit_out.lower() or "file changed" in commit_out.lower():
            # 提取统计信息
            lines_changed = commit_out.split("\n")[0] if commit_out else ""
            return f"✅ 提交成功: {message}\n{lines_changed}"
        return commit_out

    # --- log ---
    if cmd == "log":
        log_args = ["log", "--oneline", "--graph", "--decorate"]
        if args:
            log_args += args.split()
        else:
            log_args += ["-20"]  # 默认最近20条
        out = _run(log_args)
        if "fatal" in out.lower() and "does not have any commits" in out.lower():
            return "📭 仓库还没有提交记录"
        return f"📜 提交历史:\n\n{out}"

    # --- branch ---
    if cmd == "branch":
        if args:
            # 创建并切换分支
            create_out = _run(["checkout", "-b", args])
            return f"🌿 创建并切换到分支: {args}\n{create_out}"
        else:
            out = _run(["branch", "-a"])
            current = _run(["branch", "--show-current"])
            branches = [l.strip() for l in out.split("\n") if l.strip()]
            result = "🌿 分支列表:\n"
            for b in branches:
                if b.startswith("* ") or b == current:
                    result += f"   ✅ {b}\n"
                else:
                    result += f"      {b}\n"
            return result.strip()

    # --- push ---
    if cmd == "push":
        push_args = ["push"]
        if args:
            push_args += args.split()
        out = _run(push_args)
        return f"📤 Push 结果:\n{out}"

    # --- pull ---
    if cmd == "pull":
        pull_args = ["pull"]
        if args:
            pull_args += args.split()
        out = _run(pull_args)
        return f"📥 Pull 结果:\n{out}"

    # --- remote ---
    if cmd == "remote":
        if args:
            # remote add <name> <url> / remote remove <name> / remote set-url <name> <url>
            parts = args.split()
            sub = parts[0] if parts else ""
            if sub == "add" and len(parts) >= 3:
                out = _run(["remote", "add", parts[1], parts[2]])
                return f"🔗 添加远程仓库 {parts[1]}: {parts[2]}\n{out}"
            elif sub == "remove" and len(parts) >= 2:
                out = _run(["remote", "remove", parts[1]])
                return f"🗑️ 移除远程仓库 {parts[1]}\n{out}"
            elif sub == "set-url" and len(parts) >= 3:
                out = _run(["remote", "set-url", parts[1], parts[2]])
                return f"🔗 修改远程仓库 {parts[1]} URL: {parts[2]}\n{out}"
            else:
                return "❌ remote 用法: remote / remote add <name> <url> / remote remove <name> / remote set-url <name> <url>"
        # 无参数 — 列出远程仓库
        out = _run(["remote", "-v"])
        if not out or out == "(无输出)":
            return "🔗 未配置远程仓库"
        return f"🔗 远程仓库:\n{out}"

    # --- ssh ---
    if cmd == "ssh":
        parts = args.split()
        sub = parts[0] if parts else "status"
        ssh_dir = os.path.expanduser("~/.ssh")
        key_path = os.path.join(ssh_dir, "id_ed25519")
        pub_path = key_path + ".pub"

        if sub == "status":
            status_lines = []
            # 检查目录是否存在
            if not os.path.isdir(ssh_dir):
                return "🔑 SSH 目录 (~/.ssh) 不存在"
