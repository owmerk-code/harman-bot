"""Claude Code ve Codex CLI'larını abonelikle çağırır (API anahtarı YOK, ek ücret YOK).

Komut bayrakları eski sistemdekiyle BİREBİR aynı (QUANTBOT engine/ai/lab/clients.py, 2 Ekim 2026):
araçlar kapalı, boş geçici klasör, görev stdin'den, oturum kaydı yok. Abonelik CLI'ları API anahtarı görürse
ücretli API'ye geçebilir; bu yüzden o anahtarlar alt sürece verilmez.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time

# pythonw (konsolsuz) altinda claude/codex her cagride bos pencere acmasin.
_PENCERE_YOK = getattr(subprocess, "CREATE_NO_WINDOW", 0)
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harman.config import CODEX_EXE

CLAUDE, CODEX = "claude_cli", "codex_cli"
CODEX_DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "apps", "browser_use", "browser_use_external", "computer_use", "image_generation",
    "in_app_browser", "multi_agent", "hooks", "plugins", "goals", "remote_plugin", "tool_suggest",
    "workspace_dependencies", "skill_mcp_dependency_install",
)
_API_KEY_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class CallError(Exception):
    pass


@dataclass(frozen=True)
class Model:
    id: str
    provider: str
    model: str


@dataclass(frozen=True)
class Result:
    text: str
    model: str
    latency_ms: int


def _short(text: Any) -> str:
    return " ".join(_ANSI.sub("", str(text or "")).split())[:150]


def find_cli(provider: str) -> list[str] | None:
    if provider == CODEX:
        configured = os.environ.get("CODEX_CLI_PATH", "")
        if configured and Path(configured).is_file():
            return [configured]
        if CODEX_EXE.is_file():
            return [str(CODEX_EXE)]
        found = shutil.which("codex")
        return [found] if found else None
    found = shutil.which("claude")
    if not found:
        return None
    exe = Path(found).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    return [str(exe)] if exe.is_file() else [found]  # Windows'ta .cmd sarmalayıcı tırnak sorunu çıkarır


def available(m: Model) -> bool:
    return find_cli(m.provider) is not None


def _json_lines(stdout: str) -> list[dict[str, Any]]:
    out = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            out.append(event)
    return out


def parse_claude(returncode: int, stdout: str, stderr: str) -> str:
    results = [e for e in _json_lines(stdout) if e.get("type") == "result"]
    if not results:
        raise CallError(_short(stderr or stdout or f"exit {returncode}"))
    text = str(results[-1].get("result") or "").strip()
    if results[-1].get("is_error") or not text:
        raise CallError(_short(text or results[-1].get("subtype") or "bos cevap"))
    return text


def parse_codex(returncode: int, stdout: str, stderr: str) -> str:
    texts, failure = [], ""
    for event in _json_lines(stdout):
        kind = event.get("type")
        if kind == "item.completed" and (event.get("item") or {}).get("type") == "agent_message":
            texts.append(str(event["item"].get("text") or ""))
        elif kind == "turn.failed":
            message = (event.get("error") or {}).get("message") or ""
            try:
                message = json.loads(message).get("error", {}).get("message") or message
            except (ValueError, AttributeError):
                pass
            failure = str(message)
    text = texts[-1].strip() if texts else ""  # son ajan mesajı asıl cevap
    if failure or not text:
        raise CallError(_short(failure or stderr or ("bos cevap" if returncode == 0 else f"exit {returncode}")))
    return text


class CliClient:
    def __init__(self, m: Model, *, timeout: float = 180.0, run: Any = None) -> None:
        self.m, self.timeout, self._run = m, timeout, run or subprocess.run

    def complete(self, *, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 2000) -> Result:
        prefix = find_cli(self.m.provider)
        if not prefix:
            raise CallError(f"{self.m.provider} CLI bulunamadi")
        message = (system + "\n\nJSON semasi:\n" + json.dumps(schema) + "\n\n" + prompt
                   + "\n\nArac kullanma; yalniz istenen JSON nesnesini dondur.")
        env = {k: v for k, v in os.environ.items() if k.upper() not in _API_KEY_ENV}
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="harman_", ignore_cleanup_errors=True) as tmp:
            if self.m.provider == CLAUDE:
                cmd = [*prefix, "-p", "--tools", "", "--strict-mcp-config", "--setting-sources", "project",
                       "--no-session-persistence", "--output-format", "json", "--model", self.m.model]
            else:
                disabled = [a for f in CODEX_DISABLED_FEATURES for a in ("--disable", f)]
                cmd = [*prefix, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
                       "--ignore-user-config", "--ignore-rules", *disabled, "--json", "-C", tmp, "-m", self.m.model, "-"]
            try:
                proc = self._run(cmd, input=message, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=self.timeout, env=env, cwd=tmp, check=False,
                                 creationflags=_PENCERE_YOK)
            except subprocess.TimeoutExpired as exc:
                raise CallError("zaman asimi") from exc
            except OSError as exc:
                raise CallError(type(exc).__name__) from exc
        parse = parse_claude if self.m.provider == CLAUDE else parse_codex
        return Result(parse(proc.returncode, proc.stdout or "", proc.stderr or ""), self.m.model,
                      int((time.monotonic() - started) * 1000))
