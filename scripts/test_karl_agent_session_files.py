#!/usr/bin/env python3
"""Tests RM2659 — l'onglet fichiers d'une session : racines de projet, multi-projets,
`tasks/` masqué.

Trois choses à verrouiller :
  1. une session touche parfois PLUSIEURS projets (7 sur 62 au registre) — le
     cas est monté ici de toutes pièces, car il ne s'observe plus en direct :
     le GC de RM2566 a supprimé les worktrees des sessions concernées ;
  2. `.mmi-pm/tasks` (≈1 300 fiches) est masqué, mais `docs/` reste visible —
     c'est la demande, et l'inverse serait pire que l'état d'avant ;
  3. la liste blanche des racines lisibles s'ÉTEND, elle ne s'ouvre pas.

Lancer : python3 scripts/test_karl_agent_session_files.py
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


def workspace(root: pathlib.Path, client: str, slug: str, docs=("a.md", "b.md")):
    """Un workspace au layout RM1993 : `.mmi-pm/` co-localisé, envs/, repos/."""
    mmi = root / ".mmi-pm"
    (mmi / "tasks").mkdir(parents=True)
    (mmi / "docs").mkdir()
    (mmi / "project").mkdir()
    (mmi / "meta.yml").write_text(f"schema_version: 1.7.1\nslug: {slug}\nclient: {client}\n",
                                  encoding="utf-8")
    for i in range(3):
        (mmi / "tasks" / f"RM{i}_x.md").write_text("x", encoding="utf-8")
    for d in docs:
        (mmi / "docs" / d).write_text("doc", encoding="utf-8")
    (root / "envs").mkdir()
    (root / "repos").mkdir()
    return root


tmp = pathlib.Path(tempfile.mkdtemp())
ws1 = workspace(tmp / "clientA" / "appli", "clienta", "appli")
ws2 = workspace(tmp / "clientB" / "infra", "clientb", "infra")
wt1 = ws1 / "envs" / "appli-rm42"
wt1.mkdir()

# `_project_doc_roots` lit sous PROJECTS_BASE ; ici les projets PM sont les
# `.mmi-pm/` eux-mêmes (co-localisation RM1949), reproduite par des liens.
base = tmp / "projects" / "clients"
for w, client, slug in ((ws1, "clienta", "appli"), (ws2, "clientb", "infra")):
    (base / client / "projects").mkdir(parents=True, exist_ok=True)
    (base / client / "projects" / slug).symlink_to(w / ".mmi-pm")
ka.PROJECTS_BASE = base

# — remontée vers la racine —
check("un worktree sous envs/ remonte à la racine du workspace",
      ka._workspace_root(wt1) == ws1.resolve())
check("la racine se remonte elle-même", ka._workspace_root(ws1) == ws1.resolve())
check("hors de tout workspace, rien n'est deviné", ka._workspace_root(tmp) is None)
check("un chemin inexistant ne fait pas tomber", ka._workspace_root(tmp / "nope") is None)

# — racine → (client, projet), via meta.yml —
check("le couple vient du manifeste, pas du nom de dossier",
      ka._root_project(ws1) == ("clienta", "appli"))
mauvais = workspace(tmp / "x" / "cassé", "c", "s")
(mauvais / ".mmi-pm" / "meta.yml").write_text("slug: [oups\n", encoding="utf-8")
check("un meta.yml cassé ne fait pas tomber le cockpit", ka._root_project(mauvais) is None)
(mauvais / ".mmi-pm" / "meta.yml").write_text("slug: ../evasion\nclient: c\n", encoding="utf-8")
check("un slug hors motif est refusé", ka._root_project(mauvais) is None)

# — les projets de la session —
ka._key_info = lambda sid: {"session_id": "cs-1", "cwd": str(ws1)}
ka._session_worktrees = lambda sid: [str(wt1)]
prs = ka._session_projects("RM42")
check("un seul projet quand tout vient du même workspace", len(prs) == 1)
check("et il est identifié", prs[0]["client"] == "clienta" and prs[0]["project"] == "appli")
check("sa doc est jointe", {d["name"] for d in prs[0]["docs"]} == {"docs", "project"})
check("avec le nombre de documents", next(d for d in prs[0]["docs"] if d["name"] == "docs")["docs"] == 2)

# LE cas visé : la session travaille sur deux projets à la fois
ka._session_worktrees = lambda sid: [str(wt1), str(ws2)]
prs = ka._session_projects("RM42")
check("deux projets sont listés, pas un seul",
      sorted(p["project"] for p in prs) == ["appli", "infra"])
check("l'ordre part du cwd de la session", prs[0]["project"] == "appli")
ka._session_worktrees = lambda sid: [str(wt1), str(ws1), str(wt1)]
check("un projet vu plusieurs fois n'est compté qu'une",
      len(ka._session_projects("RM42")) == 1)
ka._key_info = lambda sid: {"session_id": "cs-1", "cwd": "/etc"}
ka._session_worktrees = lambda sid: []
check("une session hors workspace ne produit aucun projet",
      ka._session_projects("RM42") == [])

# — masquage : un chemin, pas un nom —
check("`.mmi-pm/tasks` est masqué", ka._fs_hide(".mmi-pm", "tasks") is True)
check("mais `.mmi-pm/docs` reste visible", ka._fs_hide(".mmi-pm", "docs") is False)
check("`project`, `memory`, `meta.yml` aussi",
      not any(ka._fs_hide(".mmi-pm", n) for n in ("project", "memory", "meta.yml")))
check("un `tasks/` DANS DU CODE reste visible — le masquage vise un chemin",
      ka._fs_hide("", "tasks") is False and ka._fs_hide("src", "tasks") is False
      and ka._fs_hide("src/.mmi-pm", "tasks") is False)
check("le `.git` reste masqué partout", ka._fs_hide("", ".git") is True)
check("une barre de trop ne contourne pas le masquage",
      ka._fs_hide("/.mmi-pm/", "tasks") is True)

# — la liste blanche s'étend, elle ne s'ouvre pas —
ka._key_info = lambda sid: {"session_id": "cs-1", "cwd": str(ws1)}
ka._session_worktrees = lambda sid: [str(wt1)]
check("la racine du projet devient lisible",
      ka._resolve_worktree("RM42", str(ws1)) == ws1)
# La doc est déclarée sous PROJECTS_BASE (chemin du projet PM), pas sous la
# racine du workspace : deux écritures du même dossier. La liste blanche compare
# des chaînes — le front doit donc utiliser les chemins que le serveur donne,
# et c'est ce que ce test exerce.
doc = next(d["path"] for d in ka._session_projects("RM42")[0]["docs"] if d["name"] == "docs")
check("sa doc aussi", ka._resolve_worktree("RM42", doc).name == "docs")
check("et l'autre écriture du même dossier n'est PAS un passe-droit",
      doc != str(ws1 / ".mmi-pm" / "docs"))
for interdit in ("/etc", "/", str(tmp), str(ws2), str(ws1) + "/..",
                 str(ws1 / ".mmi-pm" / "tasks")):
    try:
        ka._resolve_worktree("RM42", interdit)
        ok = False
    except ka.ApiError as e:
        ok = e.code == 403
    check("refusé hors périmètre : %s" % interdit[-38:], ok)

# Masqué ne doit pas vouloir dire seulement « pas cliquable » : un dossier
# qu'on atteint en devinant son chemin n'est pas masqué du tout.
check("le chemin masqué est reconnu comme tel",
      ka._fs_hidden_path(".mmi-pm/tasks") is True
      and ka._fs_hidden_path(".mmi-pm/tasks/RM1_x.md") is True)
check("et ses voisins ne le sont pas",
      not any(ka._fs_hidden_path(x) for x in ("", ".mmi-pm", ".mmi-pm/docs", "src/tasks")))
for masqué in (".mmi-pm/tasks", ".mmi-pm/tasks/RM1_x.md"):
    try:
        ka.op_fs_ls("RM42", str(ws1), masqué)
        ok = False
    except ka.ApiError as e:
        ok = e.code == 403
    check("servir %s est refusé, pas seulement caché" % masqué, ok)
ls = ka.op_fs_ls("RM42", str(ws1), ".mmi-pm")
noms = {e["name"] for e in ls["entries"]}
check("le listing de .mmi-pm ne montre pas tasks", "tasks" not in noms)
check("mais montre docs et project", {"docs", "project"} <= noms)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests onglet fichiers de session RM2659 passent")
