#!/usr/bin/env python3
"""Tests RM2360 — garde de cible de pm-branch-start (_is_core).

Sans réseau : on fabrique des repos git en tmpdir et on vérifie que la détection
de CORE (repo qui révisionne `.mmi-pm`) distingue bien le core du repo de code,
y compris le cas legacy (`.mmi-pm` symlink gitignoré = non tracké = pas un core).

Lancer : python3 scripts/test_pm_branch_start_guard.py
"""
import importlib.util
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent

# Module à tirets → chargement par chemin.
spec = importlib.util.spec_from_file_location("pm_branch_start", HERE / "pm-branch-start.py")
pbs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pbs)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def git(*a, cwd):
    subprocess.run(["git", *a], cwd=str(cwd), check=True, capture_output=True, text=True)


def init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git("init", "-q", ".", cwd=path)
    git("config", "user.email", "t@t", cwd=path)
    git("config", "user.name", "t", cwd=path)
    return path


def commit_all(path, msg="seed"):
    git("add", "-A", ".", cwd=path)
    git("commit", "-q", "-m", msg, cwd=path)


def test_core_tracks_mmi_pm(tmp):
    """Un repo qui révisionne .mmi-pm/ est un core."""
    core = init_repo(tmp / "core")
    (core / ".mmi-pm").mkdir()
    (core / ".mmi-pm" / "project").mkdir()
    (core / ".mmi-pm" / "project" / "overview.md").write_text("x\n", encoding="utf-8")
    commit_all(core)
    check("core (tracke .mmi-pm) → _is_core True", pbs._is_core(core) is True)


def test_code_repo_not_core(tmp):
    """Un repo de code (pas de .mmi-pm tracké) n'est pas un core."""
    code = init_repo(tmp / "code")
    (code / "src").mkdir()
    (code / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
    commit_all(code)
    check("repo de code → _is_core False", pbs._is_core(code) is False)


def test_legacy_symlink_not_core(tmp):
    """Modèle legacy : .mmi-pm est un symlink gitignoré du workspace de code —
    non tracké, donc PAS détecté comme core (pas de faux positif)."""
    ext = tmp / "external_pm_data"
    ext.mkdir()
    code = init_repo(tmp / "legacy")
    (code / ".gitignore").write_text(".mmi-pm\n", encoding="utf-8")
    (code / "src").mkdir()
    (code / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
    commit_all(code)
    (code / ".mmi-pm").symlink_to(ext)          # symlink gitignoré, non tracké
    check("legacy (.mmi-pm symlink gitignoré) → _is_core False", pbs._is_core(code) is False)


def test_client_core(tmp):
    """Un core client révisionne .mmi-pm-client."""
    core = init_repo(tmp / "client_core")
    (core / ".mmi-pm-client").mkdir()
    (core / ".mmi-pm-client" / "overview.md").write_text("x\n", encoding="utf-8")
    commit_all(core)
    check("core client (tracke .mmi-pm-client) → _is_core True", pbs._is_core(core) is True)


def test_peek_frontmatter(tmp):
    md = tmp / "RM1_x.md"
    md.write_text("---\ngit:\n  repo: worm-web-orm-dev\n---\ncorps\n", encoding="utf-8")
    fm = pbs.peek_task_frontmatter(md)
    check("peek_task_frontmatter lit git.repo",
          (fm.get("git") or {}).get("repo") == "worm-web-orm-dev")
    check("peek_task_frontmatter sur fichier absent → {}",
          pbs.peek_task_frontmatter(tmp / "absent.md") == {})


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        test_core_tracks_mmi_pm(tmp)
        test_code_repo_not_core(tmp)
        test_legacy_symlink_not_core(tmp)
        test_client_core(tmp)
        test_peek_frontmatter(tmp)
    print()
    if fails:
        print(f"ÉCHEC : {len(fails)} test(s) — {', '.join(fails)}")
        sys.exit(1)
    print("OK — tous les tests passent")


if __name__ == "__main__":
    main()
