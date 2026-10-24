r"""Bot verisini GitHub'daki GİZLİ depoya yedekler ('veri-yedek' dalı). PC giderse en fazla 1 günlük veri kaybolur.

Kullanım:
    .venv\Scripts\python.exe scripts\yedekle.py            # yedekle
    .venv\Scripts\python.exe scripts\yedekle.py --geri-al  # yeni bilgisayarda: son yedeği data\harman.db'ye indir

Kod 'main' dalında, veri 'veri-yedek' dalında durur; ikisi karışmaz. Yedek gzip'li ("harman.db.gz")
gönderilir (GitHub 100 MB dosya sınırı nedeniyle — DB 24 Ekim'de 100 MB üstüne çıktı).
Şifreler (.env) ASLA yedeklenmez.
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harman.config import DATA, DB  # noqa: E402

BRANCH = "veri-yedek"
WORK = DATA / "yedek_repo"
EXTRA = ROOT / "arsiv_arena"   # eski arena arşivi (bir kez yüklenir, sonra değişmez)


def git(*args: str, cwd: Path = WORK, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=check,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def remote_url() -> str:
    return git("remote", "get-url", "origin", cwd=ROOT).stdout.strip()


def prepare() -> None:
    if (WORK / ".git").exists():
        git("fetch", "-q", "origin", BRANCH, check=False)
        git("reset", "-q", "--hard", f"origin/{BRANCH}", check=False)
        return
    WORK.mkdir(parents=True, exist_ok=True)
    git("init", "-q")
    git("remote", "add", "origin", remote_url())
    if git("fetch", "-q", "origin", BRANCH, check=False).returncode == 0:
        git("checkout", "-q", "-B", BRANCH, f"origin/{BRANCH}")
    else:
        git("checkout", "-q", "--orphan", BRANCH)


def snapshot_db(target: Path) -> None:
    """Çalışan veritabanının tutarlı kopyası (SQLite yedek API'si; yarım yazılmış dosya kopyalanmaz)."""
    src, dst = sqlite3.connect(str(DB)), sqlite3.connect(str(target))
    with dst:
        src.backup(dst)
    src.close()
    dst.close()


GZ = WORK / "harman.db.gz"


def pack_db() -> None:
    """Canli DB'nin tutarlı kopyası -> küçült (kopyada VACUUM) -> WORK/harman.db.gz.

    GitHub tek dosyada 100 MB üstünü reddediyor; DB 24 Ekim'de ~103 MB'a çıkınca
    düz dosya gönderimi başarısız olmaya başladı. Sıkıştırma çözümü:
    kopyada VACUUM (boş sayfalar atılır) sonra gzip (canli DB'ye dokunulmaz).
    """
    tmp = DATA / "yedek_gecici.db"
    snapshot_db(tmp)
    conn = sqlite3.connect(str(tmp))
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()
    with open(tmp, "rb") as f, gzip.open(GZ, "wb", compresslevel=6) as out:
        shutil.copyfileobj(f, out, length=1024 * 1024)
    tmp.unlink()
    # Eski (sikistirmasiz) harman.db izleniyorsa yeni committen cikarilir.
    raw = WORK / "harman.db"
    if raw.exists():
        raw.unlink()


def backup() -> str:
    if not DB.exists():
        return "veritabani yok; yedeklenecek sey yok"
    prepare()
    pack_db()
    if EXTRA.exists() and not (WORK / "arsiv_arena").exists():
        shutil.copytree(EXTRA, WORK / "arsiv_arena")
    (WORK / "BENIOKU.txt").write_text(
        "HARMAN veri yedegi. Icerik: harman.db.gz (sikistirilmis SQLite veritabani).\n"
        "Geri yuklemek icin: scripts\\yedekle.py --geri-al\n"
        "Bu dalda kod yoktur; kod 'main' dalindadir. Sifreler (.env) burada YOKTUR.\n", encoding="utf-8")
    git("add", "-A")
    if not git("status", "--porcelain").stdout.strip():
        return "degisiklik yok"
    git("-c", "user.name=HARMAN bot", "-c", "user.email=harman-bot@localhost", "commit", "-q", "-m",
        f"Yedek {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    push = git("push", "-q", "origin", f"HEAD:{BRANCH}", check=False)
    if push.returncode != 0:
        raise RuntimeError("push basarisiz: " + (push.stderr or push.stdout)[:200])
    return "gonderildi"


def restore() -> str:
    prepare()
    gz = WORK / "harman.db.gz"
    raw = WORK / "harman.db"
    tmp = DATA / "yedek_geri.db"
    if gz.exists():
        with gzip.open(gz, "rb") as f:
            tmp.write_bytes(f.read())
    elif raw.exists():  # eski (sikistirmasiz) yedek formati — uyumluluk
        shutil.copy2(raw, tmp)
    else:
        return "GitHub'da yedek bulunamadi"
    check = sqlite3.connect(str(tmp))
    try:
        state = check.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        check.close()
    if state != "ok":
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"yedek bozuk gorunuyor ({state})")
    if DB.exists():
        DB.rename(DB.with_suffix(f".db.eski-{datetime.now():%Y%m%d%H%M%S}"))
    shutil.copy2(tmp, DB)
    tmp.unlink()
    if (WORK / "arsiv_arena").exists() and not EXTRA.exists():
        shutil.copytree(WORK / "arsiv_arena", EXTRA)
    return f"geri yuklendi: {DB}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geri-al", action="store_true")
    args = ap.parse_args(argv)
    try:
        print(restore() if args.geri_al else backup())
        return 0
    except Exception as exc:
        print(f"HATA: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
