"""Bağımsız parçalar: CLI AI çağrısı, haber okuyucu, .env, Telegram, yedek (ağ/AI YOK)."""
from __future__ import annotations

import json
import sqlite3
import subprocess

import pytest

from harman import cli_ai, config, news, telegram
from harman.cli_ai import CLAUDE, CODEX, CallError, CliClient, Model


# ------------------------------------------------------------------ CLI AI
def test_claude_command_has_tools_off_and_no_api_keys(monkeypatch):
    monkeypatch.setattr(cli_ai, "find_cli", lambda p: ["claude.exe"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "gizli")
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["env"], seen["input"] = cmd, kw["env"], kw["input"]
        out = json.dumps({"type": "result", "result": '{"karar": "devam"}'})
        return subprocess.CompletedProcess(cmd, 0, out, "")

    res = CliClient(Model("x", CLAUDE, "claude-sonnet-5-5"), run=run).complete(system="S", prompt="P", schema={})
    assert res.text == '{"karar": "devam"}'
    cmd = seen["cmd"]
    assert cmd[cmd.index("--tools") + 1] == "" and "--no-session-persistence" in cmd
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5-5"
    assert "ANTHROPIC_API_KEY" not in seen["env"]            # abonelik yerine ücretli API'ye kaçmasın
    assert "Arac kullanma" in seen["input"]


def test_codex_command_is_read_only_and_tools_disabled(monkeypatch):
    monkeypatch.setattr(cli_ai, "find_cli", lambda p: ["codex.exe"])
    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        ev = [{"type": "item.completed", "item": {"type": "agent_message", "text": "ara"}},
              {"type": "item.completed", "item": {"type": "agent_message", "text": '{"reddet": []}'}}]
        return subprocess.CompletedProcess(cmd, 0, "\n".join(json.dumps(e) for e in ev), "")

    res = CliClient(Model("x", CODEX, "gpt-6.1-sol"), run=run).complete(system="S", prompt="P", schema={})
    assert res.text == '{"reddet": []}'                      # son ajan mesajı asıl cevap
    cmd = seen["cmd"]
    assert cmd[cmd.index("--sandbox") + 1] == "read-only" and "shell_tool" in cmd and "--ephemeral" in cmd


def test_cli_errors_are_reported_not_swallowed():
    with pytest.raises(CallError):
        cli_ai.parse_claude(1, json.dumps({"type": "result", "is_error": True, "result": "limit"}), "")
    with pytest.raises(CallError):
        cli_ai.parse_codex(0, json.dumps({"type": "turn.failed", "error": {"message": "401"}}), "")


# ------------------------------------------------------------------ haberler
RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Bitcoin ETF inflows rise</title><guid>a1</guid><pubDate>Thu, 01 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title></title><guid>bos</guid></item>
</channel></rss>"""


def test_rss_parsing():
    (item,) = news.parse_feed("Test", RSS)
    assert item["t"] == "[Test] Bitcoin ETF inflows rise" and item["id"] == "a1" and item["ms"] > 0


# ------------------------------------------------------------------ .env ve Telegram
def test_env_reader(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# yorum\nTELEGRAM_BOT_TOKEN="abc"\nTELEGRAM_CHAT_ID=42\nBOS\n', encoding="utf-8")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert config.load_env(f) == {"TELEGRAM_BOT_TOKEN": "abc", "TELEGRAM_CHAT_ID": "42"}


def test_telegram_without_settings_does_not_crash(monkeypatch):
    monkeypatch.setattr(telegram, "setting", lambda name, default="": "")
    assert telegram.send("x") is False


def test_telegram_posts_to_the_right_chat(monkeypatch):
    monkeypatch.setattr(telegram, "setting", lambda n, d="": {"TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_CHAT_ID": "9"}[n])
    sent = {}

    class C:
        def post(self, url, json):
            sent["url"], sent["json"] = url, json

            class R:
                status_code = 200

                @staticmethod
                def json():
                    return {"ok": True}
            return R()

    assert telegram.send("merhaba", client=C()) is True
    assert sent["url"].endswith("/botT/sendMessage") and sent["json"]["chat_id"] == "9"


# ------------------------------------------------------------------ yedek
def test_backup_copy_is_a_consistent_sqlite_file(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("yedekle", config.ROOT / "scripts" / "yedekle.py")
    y = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(y)
    src = tmp_path / "harman.db"
    con = sqlite3.connect(str(src))
    con.execute("CREATE TABLE t(x)")
    con.execute("INSERT INTO t VALUES (7)")
    con.commit()
    con.close()
    monkeypatch.setattr(y, "DB", src)
    y.snapshot_db(tmp_path / "kopya.db")
    assert sqlite3.connect(str(tmp_path / "kopya.db")).execute("SELECT x FROM t").fetchone() == (7,)


def test_secrets_never_go_to_github():
    ignored = (config.ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for must in (".env", "data/", "tools/", ".venv/", "logs/"):
        assert must in ignored, must
