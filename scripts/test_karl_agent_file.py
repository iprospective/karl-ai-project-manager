#!/usr/bin/env python3
"""Tests RM2303 — op_file : servir les docs d'un projet symlinké, sans ouvrir
d'évasion URL (`..`, chemin absolu, hors projects/, non-.md).

Lancer : python3 scripts/test_karl_agent_file.py
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


def check(name, fn, expect):
    """expect : contenu attendu (str) ou code ApiError attendu (int)."""
    try:
        out = fn()
        ok = isinstance(expect, str) and out == expect
        got = "contenu" if ok else f"contenu inattendu {out!r}"
    except ka.ApiError as e:
        ok = isinstance(expect, int) and e.code == expect
        got = f"ApiError {e.code}"
    print(("✓ " if ok else "✗ ") + f"{name} (attendu {expect!r}, obtenu {got})")
    if not ok:
        fails.append(name)


with tempfile.TemporaryDirectory() as td:
    tmp = pathlib.Path(td)
    root = tmp / "repo"
    # projet « réel » sous projects/
    real = root / "projects/clients/c/projects/real/project"
    real.mkdir(parents=True)
    (real / "overview.md").write_text("doc réel", encoding="utf-8")
    # projet « relocalisé » : symlink vers un dossier PM hors du repo (modèle
    # pm-sync-links / .mmi-pm de workspace) — le cas du bug (403 avant correction)
    outside = tmp / "outside/pmdir"
    (outside / "project").mkdir(parents=True)
    (outside / "project" / "overview.md").write_text("doc symlinké", encoding="utf-8")
    (root / "projects/clients/c/projects/linked").symlink_to(outside)
    # appât hors de projects/ pour les tests d'évasion
    (root / "secret.md").write_text("secret", encoding="utf-8")

    ka.REPO_ROOT = root

    check("doc d'un projet réel servi",
          lambda: ka.op_file("projects/clients/c/projects/real/project/overview.md"), "doc réel")
    check("doc d'un projet SYMLINKÉ servi (bug RM2303)",
          lambda: ka.op_file("projects/clients/c/projects/linked/project/overview.md"), "doc symlinké")
    check("traversée .. refusée",
          lambda: ka.op_file("projects/../secret.md"), 403)
    check("chemin absolu refusé",
          lambda: ka.op_file("/etc/hostname"), 403)
    check("hors de projects/ refusé",
          lambda: ka.op_file("secret.md"), 403)
    check("non-.md refusé",
          lambda: ka.op_file("projects/clients/c/projects/real/project/overview.txt"), 404)
    check("path vide refusé",
          lambda: ka.op_file(""), 400)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests op_file RM2303 passent")
