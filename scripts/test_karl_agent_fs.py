#!/usr/bin/env python3
"""Tests RM2586 — explorateur de fichiers (worktrees de la session, lecture seule).

Unitaire : fonctions pures (_ls_sort, _parse_gitlog), gardes de chemin
(_safe_subpath), whitelist worktree, et op_fs_* sur un worktree fabriqué en tmp.
Lancer : python3 scripts/test_karl_agent_fs.py
"""
import importlib.util
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def raises(code, fn):
    try:
        fn()
        return False
    except ka.ApiError as e:
        return e.code == code


# — _ls_sort : dossiers d'abord, alpha insensible à la casse —
_ls = ka._ls_sort([{"name": "b.txt", "dir": False}, {"name": "Zeta", "dir": True},
                   {"name": "alpha", "dir": True}, {"name": "A.md", "dir": False}])
check("dossiers avant fichiers", [e["name"] for e in _ls][:2] == ["alpha", "Zeta"])
check("alpha insensible à la casse dans chaque groupe",
      [e["name"] for e in _ls] == ["alpha", "Zeta", "A.md", "b.txt"])
check("_ls_sort tolère vide", ka._ls_sort([]) == [] and ka._ls_sort(None) == [])

# — _parse_gitlog —
_txt = "abc123\x1fMathieu\x1f2026-08-09\x1fpm(RM1): x\nmalformé sans séparateurs\ndef456\x1fKarl\x1f2026-08-08\x1ffix: y"
_cm = ka._parse_gitlog(_txt)
check("parse_gitlog garde les lignes valides", len(_cm) == 2)
check("parse_gitlog champs corrects",
      _cm[0] == {"hash": "abc123", "author": "Mathieu", "date": "2026-08-09", "subject": "pm(RM1): x"})
check("parse_gitlog subject avec séparateurs internes tolère",
      ka._parse_gitlog("h\x1fa\x1fd\x1fsujet: ok")[0]["subject"] == "sujet: ok")
check("parse_gitlog vide", ka._parse_gitlog("") == [] and ka._parse_gitlog(None) == [])

# — worktree fabriqué + whitelist de session (monkeypatch) —
wt = tempfile.mkdtemp(prefix="rm2586-wt-")
base = pathlib.Path(wt)
(base / "src").mkdir()
(base / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
(base / "README.md").write_text("# Titre\n", encoding="utf-8")
(base / ".git").mkdir()                       # doit être masqué
(base / "bin.dat").write_bytes(b"\x00\x01\x02")
ka._session_worktrees = lambda sid: [wt]      # whitelist = ce worktree

# _resolve_worktree
check("worktree de la session accepté", ka._resolve_worktree("s", wt) == base)
check("worktree hors session → 403", raises(403, lambda: ka._resolve_worktree("s", "/etc")))

# _safe_subpath : évasion refusée
check("sous-chemin absolu → 403", raises(403, lambda: ka._safe_subpath(base, "/etc/passwd")))
check("sous-chemin .. → 403", raises(403, lambda: ka._safe_subpath(base, "../x")))
check("sous-chemin normal accepté", ka._safe_subpath(base, "src/app.py") == base / "src" / "app.py")

# op_fs_ls : dossiers d'abord, .git masqué
_lsr = ka.op_fs_ls("s", wt, "")
names = [e["name"] for e in _lsr["entries"]]
check("op_fs_ls masque .git", ".git" not in names)
check("op_fs_ls dossier src listé en tête", names[0] == "src" and "README.md" in names)

# op_fs_file : lecture, markdown flag, binaire refusé, trop gros
_f = ka.op_fs_file("s", wt, "README.md")
check("op_fs_file lit le contenu", _f["content"].startswith("# Titre") and _f["markdown"] is True)
check("op_fs_file binaire → 415", raises(415, lambda: ka.op_fs_file("s", wt, "bin.dat")))
check("op_fs_file inexistant → 404", raises(404, lambda: ka.op_fs_file("s", wt, "nope.txt")))
check("op_fs_ls évasion → 403", raises(403, lambda: ka.op_fs_ls("s", wt, "../..")))

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests explorateur de fichiers RM2586 passent")
