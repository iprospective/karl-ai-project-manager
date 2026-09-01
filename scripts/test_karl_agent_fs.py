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

# — RM2590 : périmètre PROJET (union avec la session) —
wt2 = tempfile.mkdtemp(prefix="rm2590-wt-")
(pathlib.Path(wt2) / "doc.md").write_text("# projet\n", encoding="utf-8")
ka._project_worktrees = lambda c, p: [wt2]        # whitelist projet = wt2
# wt2 n'est PAS dans la session (whitelist session = [wt]) mais l'est dans le projet
check("worktree du projet accepté (union session ∪ projet)",
      ka._resolve_worktree("s", wt2, "cli", "prj") == pathlib.Path(wt2))
check("worktree du projet refusé SANS périmètre projet",
      raises(403, lambda: ka._resolve_worktree("s", wt2)))
check("op_fs_ls périmètre projet liste wt2",
      any(e["name"] == "doc.md" for e in ka.op_fs_ls("", wt2, "", "cli", "prj")["entries"]))
check("op_fs_file périmètre projet lit wt2",
      ka.op_fs_file("", wt2, "doc.md", "cli", "prj")["content"].startswith("# projet"))
check("évasion refusée aussi en périmètre projet",
      raises(403, lambda: ka.op_fs_ls("", wt2, "..", "cli", "prj")))
check("op_project_worktrees liste les worktrees du projet",
      any(w["name"] == pathlib.Path(wt2).name for w in ka.op_project_worktrees("cli", "prj")["worktrees"]))


# — RM2673 : racines d'un projet SANS session (op_project_roots) —
# Arbo PM factice : <base>/<client>/projects/<projet>/{project,docs} + workspace
_pm = pathlib.Path(tempfile.mkdtemp(prefix="rm2673-pm-"))
_pdir = _pm / "cli" / "projects" / "prj"
(_pdir / "docs").mkdir(parents=True)
(_pdir / "project").mkdir()
(_pdir / "docs" / "a.md").write_text("# a\n", encoding="utf-8")
(_pdir / "project" / "overview.md").write_text("# o\n", encoding="utf-8")
_ws = pathlib.Path(tempfile.mkdtemp(prefix="rm2673-ws-"))
(_ws / "fichier.md").write_text("# ws\n", encoding="utf-8")
ka.PROJECTS_BASE = _pm
ka._resolve_workspace = lambda pdir: _ws
ka._project_worktrees = lambda c, p: []       # aucun worktree : le cas qui vidait le panneau

_roots = ka.op_project_roots("cli", "prj")
check("op_project_roots rend un projet", len(_roots["projects"]) == 1)
_pr = _roots["projects"][0]
check("op_project_roots : la racine du workspace", _pr["root"] == str(_ws) and _pr["exists"] is True)
check("op_project_roots : la doc du projet (project + docs)",
      {d["name"] for d in _pr["docs"]} == {"project", "docs"})
check("op_project_roots : le nombre de .md est rendu",
      all(d["docs"] == 1 for d in _pr["docs"]))
check("op_project_roots refuse un couple invalide",
      raises(400, lambda: ka.op_project_roots("../etc", "prj")))
check("op_project_roots : projet sans racine ni doc → 404",
      raises(404, lambda: ka.op_project_roots("cli", "inconnu")))
# la racine est lisible sans session, même sans worktree déclaré
check("racine du projet lisible sans session (RM2673)",
      ka._resolve_worktree("", str(_ws), "cli", "prj") == _ws)
check("op_fs_ls sur la racine du projet, sans sid",
      any(e["name"] == "fichier.md" for e in ka.op_fs_ls("", str(_ws), "", "cli", "prj")["entries"]))
check("doc du projet lisible sans session",
      any(e["name"] == "a.md" for e in ka.op_fs_ls("", str(_pdir / "docs"), "", "cli", "prj")["entries"]))
check("hors périmètre toujours refusé sans sid",
      raises(403, lambda: ka.op_fs_ls("", "/etc", "", "cli", "prj")))

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests explorateur de fichiers RM2586 passent")
