"""Attachment subsystem — file storage, user message building, directory scan."""

from __future__ import annotations

import fnmatch
import mimetypes
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from codeagent.core import env as ca_env

ATTACHMENT_TAG_RE = re.compile(
    r"\[attachment:([^\s\]]+)(?:\s+([^\]]+))?\]",
    re.IGNORECASE,
)
IMAGE_DIR_TAG_RE = re.compile(
    r"\[image_dir:([^\s\]]+)(?:\s+max=(\d+))?\]",
    re.IGNORECASE,
)

_DEFAULT_IMAGE_GLOBS = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif", "*.bmp")


@dataclass
class AttachmentMeta:
    id: str
    kind: str
    mime: str
    filename: str
    size_bytes: int
    path: str = ""
    extracted_text: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _max_count() -> int:
    return ca_env.pick_int(8, "CODEAGENT_ATTACHMENTS_MAX_COUNT")


def _max_bytes() -> int:
    return ca_env.pick_int(20 * 1024 * 1024, "CODEAGENT_ATTACHMENTS_MAX_BYTES")


def _dir_max_files() -> int:
    return ca_env.pick_int(32, "CODEAGENT_ATTACHMENTS_DIR_MAX_FILES")


def _allowed_mime_prefixes() -> tuple[str, ...]:
    raw = ca_env.pick_default(
        "image/,video/,audio/,application/pdf,text/",
        "CODEAGENT_ATTACHMENTS_ALLOWED_MIME",
    )
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def mime_allowed(mime: str, filename: str = "") -> bool:
    m = (mime or "").lower().split(";")[0].strip()
    if not m and filename:
        guessed, _ = mimetypes.guess_type(filename)
        m = (guessed or "").lower()
    if m in ("image/svg+xml", "text/html"):
        return False
    for prefix in _allowed_mime_prefixes():
        if prefix.endswith("/") and m.startswith(prefix):
            return True
        if m == prefix:
            return True
    return False


def _max_bytes_for_kind(kind: str) -> int:
    k = (kind or "").lower()
    if k in ("video", "audio"):
        return ca_env.pick_int(100 * 1024 * 1024, "CODEAGENT_MEDIA_MAX_BYTES")
    return _max_bytes()


def _kind_for_mime(mime: str, filename: str) -> str:
    m = (mime or "").lower()
    if m.startswith("image/"):
        return "image"
    if m.startswith("video/"):
        return "video"
    if m.startswith("audio/"):
        return "audio"
    if m == "application/pdf" or filename.lower().endswith(".pdf"):
        return "document"
    return "document"


def extract_document_text(raw: bytes, mime: str, filename: str = "") -> str:
    m = (mime or "").lower()
    name = (filename or "").lower()
    if m.startswith("text/") or name.endswith((".txt", ".md", ".markdown")):
        return raw.decode("utf-8", errors="replace").strip()
    if m == "application/pdf" or name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(raw))
            parts = []
            for page in reader.pages:
                t = page.extract_text() or ""
                if t.strip():
                    parts.append(t.strip())
            text = "\n\n".join(parts).strip()
            if not text:
                return "[PDF 无文本层；请转为图片后使用 vision_analyze]"
            return text
        except ImportError:
            return "[PDF 解析需要 pip install pypdf]"
        except Exception as e:
            return f"[PDF 提取失败: {e}]"
    return ""


def save_attachment(
    *,
    agent_id: str,
    session_id: str,
    raw_bytes: bytes,
    filename: str,
    mime: str = "",
) -> AttachmentMeta:
    kind_guess = _kind_for_mime(mime, filename)
    limit = _max_bytes_for_kind(kind_guess)
    if len(raw_bytes) > limit:
        raise ValueError(f"attachment exceeds {limit} bytes")
    if not mime_allowed(mime, filename):
        raise ValueError(f"mime not allowed: {mime or filename}")
    from seed.core.media_store import save_session_media

    aid, path = save_session_media(
        agent_id=agent_id,
        session_id=session_id,
        raw_bytes=raw_bytes,
        filename=filename,
        mime=mime,
    )
    kind = _kind_for_mime(mime, filename)
    extracted = None
    if kind == "document":
        extracted = extract_document_text(raw_bytes, mime, filename) or None
    return AttachmentMeta(
        id=aid,
        kind=kind,
        mime=(mime or mimetypes.guess_type(filename)[0] or "application/octet-stream"),
        filename=filename or aid,
        size_bytes=len(raw_bytes),
        path=str(path),
        extracted_text=extracted,
    )


def resolve_attachment_path(agent_id: str, session_id: str, attachment_id: str) -> Optional[Path]:
    from seed.core.media_store import resolve_session_media_path

    p = resolve_session_media_path(agent_id, session_id, attachment_id)
    return p


def load_attachment_meta(agent_id: str, session_id: str, attachment_id: str) -> Optional[AttachmentMeta]:
    p = resolve_attachment_path(agent_id, session_id, attachment_id)
    if not p or not p.is_file():
        return None
    mime, _ = mimetypes.guess_type(str(p))
    kind = _kind_for_mime(mime or "", p.name)
    return AttachmentMeta(
        id=attachment_id,
        kind=kind,
        mime=mime or "application/octet-stream",
        filename=p.name.split("_", 1)[-1] if "_" in p.name else p.name,
        size_bytes=p.stat().st_size,
        path=str(p.resolve()),
    )


def build_user_message(
    text: str,
    attachments: list[AttachmentMeta],
    *,
    image_dir_tag: str = "",
) -> dict[str, Any]:
    lines: list[str] = []
    t = (text or "").strip()
    if t:
        lines.append(t)
    elif attachments:
        lines.append("[附件]")
    for a in attachments:
        if a.kind == "document" and a.extracted_text:
            lines.append(f"[文档: {a.filename}]\n{a.extracted_text}")
        else:
            lines.append(f"[attachment:{a.id} {a.filename}]")
    if image_dir_tag.strip():
        lines.append(image_dir_tag.strip())
    msg: dict[str, Any] = {
        "role": "user",
        "content": "\n".join(lines),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if attachments:
        msg["attachments"] = [a.to_dict() for a in attachments]
    return msg


def content_text_for_skills(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        text = "".join(parts)
    else:
        text = str(content)
    text = ATTACHMENT_TAG_RE.sub("", text)
    text = IMAGE_DIR_TAG_RE.sub("", text)
    return text.strip()


def parse_image_dir_tags(text: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for m in IMAGE_DIR_TAG_RE.finditer(text or ""):
        rel = m.group(1).strip()
        try:
            mx = int(m.group(2)) if m.group(2) else _dir_max_files()
        except ValueError:
            mx = _dir_max_files()
        out.append((rel, min(mx, _dir_max_files())))
    return out


def scan_image_directory(
    workspace_root: Path,
    rel_path: str,
    *,
    pattern: Optional[str] = None,
    max_files: Optional[int] = None,
) -> tuple[list[Path], bool]:
    """Return (image paths, truncated). Paths resolved under workspace_root."""
    root = workspace_root.resolve()
    rel = (rel_path or "").strip().replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        raise ValueError("path traversal not allowed")
    target = (root / rel).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("path outside workspace")
    if not target.is_dir():
        raise ValueError(f"not a directory: {rel_path}")

    globs = _parse_globs(pattern)
    limit = max_files if max_files is not None else _dir_max_files()
    found: list[Path] = []
    truncated = False
    for dirpath, _, filenames in os.walk(target):
        for name in sorted(filenames):
            if not _matches_globs(name, globs):
                continue
            p = Path(dirpath) / name
            if not p.is_file():
                continue
            found.append(p.resolve())
            if len(found) >= limit:
                truncated = True
                return found, truncated
    return found, truncated


def _parse_globs(pattern: Optional[str]) -> tuple[str, ...]:
    if pattern and pattern.strip():
        return tuple(g.strip() for g in pattern.split(",") if g.strip())
    raw = ca_env.pick_default(
        ",".join(_DEFAULT_IMAGE_GLOBS),
        "CODEAGENT_IMAGE_DIR_ALLOWED_GLOB",
    )
    return tuple(g.strip() for g in raw.split(",") if g.strip())


def _matches_globs(name: str, globs: tuple[str, ...]) -> bool:
    low = name.lower()
    for g in globs:
        if fnmatch.fnmatch(low, g.lower()):
            return True
    return False


def message_has_image_attachments(msg: dict[str, Any]) -> bool:
    atts = msg.get("attachments")
    if isinstance(atts, list):
        for a in atts:
            if isinstance(a, dict) and a.get("kind") == "image":
                return True
    if IMAGE_DIR_TAG_RE.search(str(msg.get("content") or "")):
        return True
    return False


def message_has_video_attachments(msg: dict[str, Any]) -> bool:
    atts = msg.get("attachments")
    if isinstance(atts, list):
        for a in atts:
            if isinstance(a, dict) and a.get("kind") == "video":
                return True
    return False


def message_has_audio_attachments(msg: dict[str, Any]) -> bool:
    atts = msg.get("attachments")
    if isinstance(atts, list):
        for a in atts:
            if isinstance(a, dict) and a.get("kind") == "audio":
                return True
    return False


def collect_attachment_ids_from_message(msg: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    atts = msg.get("attachments")
    if isinstance(atts, list):
        for a in atts:
            if isinstance(a, dict) and a.get("id"):
                ids.append(str(a["id"]))
    for m in ATTACHMENT_TAG_RE.finditer(str(msg.get("content") or "")):
        ids.append(m.group(1))
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out
