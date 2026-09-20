#!/usr/bin/env python3
"""Tests RM2947 — créer un projet sous une racine client VERROUILLÉE (2750 pm:pm).

Lancer : python3 scripts/test_pm_project_new_ws_locked.py

Le bug : `pm-project-new` déléguait le squelette à `pm-env-helper ws-init` (RM2909),
lequel crée entre autres `.mmi-pm/` — puis refusait quelques lignes plus bas sur ce
même `.mmi-pm/`, « workspace déjà relié à un projet PM ». Échec systématique, et sans
sortie de secours : la racine `2750` interdit à l'appelant de retirer le dossier.

Trois blocages en enfilade, tous couverts ici :
  1. le garde-fou coloc ne distinguait pas un squelette (dossiers vides) d'un volet
     PM peuplé ;
  2. `.git` et `docs` manquaient au squelette — or les créer à la racine est
     l'écriture que `2750` réserve au privilège ;
  3. le `.gitignore` posé par `ws-init` (commenté) n'est pas celui de `git_core_publish`
     (nu) : à l'octet près, il passait pour un fichier tiers à renommer — un `rename`
     à la racine, donc `Permission denied` de plus.

Les perms réelles ne sont pas rejouables sans root : on teste la LOGIQUE qui décide,
et les garde-fous du helper sont testés à part (test-pm-env-helper-ws-init.sh).
"""
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _charge(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, str(_HERE / fichier))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


skel = _charge("pm_ws_skeleton", "pm_ws_skeleton.py")
coloc = _charge("pm_workspace_coloc", "pm-workspace-coloc.py")
# Le harnais Redmine/PMConfig existe déjà pour le modèle co-localisé : on le réutilise
# tel quel (make_cfg, fake_api_call, run_main, BASE_ARGS) plutôt que d'en refaire un.
tcoloc = _charge("test_pm_project_new_coloc", "test_pm_project_new_coloc.py")

GITIGNORE_WS_INIT = (
    "# Généré par pm-env-init (RM1947). Seul .mmi-pm/ est tracké ; tout le reste\n"
    "# (code en worktrees, bares, runtime) est local/régénérable.\n"
    "/*\n!/.gitignore\n!/.mmi-pm/\n"
)


def squelette_ws_init(ws: Path, avec_git=True):
    """Reproduit l'état dans lequel `pm-env-helper ws-init` laisse un workspace neuf :
    les dossiers du modèle (VIDES), la whitelist commentée, le dépôt -core vide et le
    lien docs. C'est l'état exact sur lequel pm-project-new butait."""
    ws.mkdir(parents=True, exist_ok=True)
    for rel in ("repos", "envs", "tmp", "sessions", "logs", "data",
                ".mmi-pm", ".mmi-pm/tasks", ".mmi-pm/docs", ".mmi-pm/memory",
                ".mmi-pm/project", ".mmi-pm/.wiki-sync"):
        (ws / rel).mkdir(parents=True, exist_ok=True)
    (ws / ".gitignore").write_text(GITIGNORE_WS_INIT, encoding="utf-8")
    if avec_git:
        subprocess.run(["git", "init", "-q", "-b", "main", str(ws)], check=True,
                       capture_output=True)
    return ws


def _client_pm(tmp: Path):
    (tmp / "clients" / "testclient" / "projects").mkdir(parents=True)


def _run(ws: Path, tmp: Path):
    return tcoloc.run_main(tcoloc.BASE_ARGS + ["--workspace", str(ws), "--dry-run"], tmp)


# ── 1. Squelette vs volet PM peuplé ─────────────────────────────────────────
def test_squelette_vide_n_est_pas_un_projet():
    with tempfile.TemporaryDirectory() as td:
        ws = squelette_ws_init(Path(td) / "ws" / "monprojet")
        assert not skel.deja_relie(ws / ".mmi-pm"), \
            "un .mmi-pm/ de dossiers vides est le squelette ws-init, pas un projet"


def test_volet_pm_peuple_reste_un_refus():
    with tempfile.TemporaryDirectory() as td:
        ws = squelette_ws_init(Path(td) / "ws" / "monprojet")
        (ws / ".mmi-pm" / "meta.yml").write_text("slug: x\n", encoding="utf-8")
        assert skel.deja_relie(ws / ".mmi-pm"), "meta.yml ⇒ workspace déjà relié"


def test_fichier_enfoui_suffit_a_refuser():
    """Un `.mmi-pm/` sans meta.yml mais avec une tâche reste un volet PM peuplé."""
    with tempfile.TemporaryDirectory() as td:
        ws = squelette_ws_init(Path(td) / "ws" / "monprojet")
        (ws / ".mmi-pm" / "tasks" / "RM1_x.md").write_text("", encoding="utf-8")
        assert skel.deja_relie(ws / ".mmi-pm")


def test_symlink_reste_un_refus_sec():
    """Ancien modèle (volet déporté sous projects/, RM2228) : refus, même vide."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cible = tmp / "ailleurs"
        cible.mkdir()
        ws = squelette_ws_init(tmp / "ws" / "monprojet")
        shutil.rmtree(ws / ".mmi-pm")
        (ws / ".mmi-pm").symlink_to(cible)
        assert skel.deja_relie(ws / ".mmi-pm"), "un .mmi-pm symlink n'est jamais un squelette"


def test_git_fait_partie_du_squelette():
    """`.git` manquant ⇒ pièce de squelette manquante : sous une racine 2750, c'est
    au helper de l'amorcer, sinon la publication meurt en Permission denied."""
    with tempfile.TemporaryDirectory() as td:
        ws = squelette_ws_init(Path(td) / "ws" / "monprojet", avec_git=False)
        assert ".git" in skel.missing_pieces(ws), skel.missing_pieces(ws)
        squelette_ws_init(ws)
        assert ".git" not in skel.missing_pieces(ws)


# ── 2. pm-project-new de bout en bout sur l'état laissé par ws-init ─────────
def test_pm_project_new_accepte_le_squelette_ws_init():
    """REPRO RM2947 : le pipeline doit aller au bout sur le workspace que ws-init
    vient de créer (squelette + .gitignore + .git vide + docs)."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _client_pm(tmp)
        ws = squelette_ws_init(tmp / "ws" / "monprojet")
        (ws / "docs").symlink_to(Path(".mmi-pm") / "docs")
        out, code = _run(ws, tmp)
        assert code in (None, 0), f"doit accepter le squelette ws-init : exit={code}\n{out}"
        assert "monprojet-core" in out, out


def test_pm_project_new_refuse_toujours_un_projet_existant():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _client_pm(tmp)
        ws = squelette_ws_init(tmp / "ws" / "monprojet")
        (ws / ".mmi-pm" / "meta.yml").write_text("slug: x\n", encoding="utf-8")
        out, code = _run(ws, tmp)
        assert code not in (None, 0), f"un volet PM peuplé doit rester un refus\n{out}"


def test_pm_project_new_refuse_toujours_un_repo_de_code():
    """Non-régression du garde-fou RM1993 : un dépôt qui a des commits est du CODE."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _client_pm(tmp)
        ws = squelette_ws_init(tmp / "ws" / "monprojet")
        (ws / "index.php").write_text("<?php\n", encoding="utf-8")
        for cmd in (["add", "-f", "--", "index.php"],
                    ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "code"]):
            subprocess.run(["git", "-C", str(ws), *cmd], check=True, capture_output=True)
        out, code = _run(ws, tmp)
        assert code not in (None, 0), f"un repo de code doit rester un refus\n{out}"
        assert "pm-env-migrate" in str(code), code


def test_pm_project_new_refuse_un_git_qui_n_est_pas_un_depot():
    """Un `.git` illisible n'est pas un `-core` vierge : on ne crée pas par-dessus."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _client_pm(tmp)
        ws = squelette_ws_init(tmp / "ws" / "monprojet", avec_git=False)
        (ws / ".git").mkdir()
        out, code = _run(ws, tmp)
        assert code not in (None, 0), f"un .git non exploitable doit rester un refus\n{out}"


# ── 3. La whitelist de ws-init n'est pas un .gitignore tiers ────────────────
def test_whitelist_commentee_equivaut_a_la_nue():
    nue = coloc.GITIGNORE.format(name=".mmi-pm")
    assert coloc.regles_gitignore(GITIGNORE_WS_INIT) == coloc.regles_gitignore(nue)
    autre = "/*\n!/.gitignore\n!/.mmi-pm-client/\n"
    assert coloc.regles_gitignore(autre) != coloc.regles_gitignore(nue), \
        "deux whitelists de volets DIFFÉRENTS ne doivent pas être confondues"


def test_git_core_publish_ne_renomme_pas_la_whitelist_de_ws_init():
    """Le fichier posé par ws-init doit être laissé en place : le renommer exigerait
    d'écrire à la racine — impossible pour l'appelant sous 2750."""
    with tempfile.TemporaryDirectory() as td:
        ws = squelette_ws_init(Path(td) / "ws" / "monprojet")
        (ws / ".mmi-pm" / "meta.yml").write_text("slug: x\n", encoding="utf-8")
        vrai_git, pousses = coloc.git, []

        def git_sans_push(folder, *args, **kw):
            if args and args[0] == "push":
                pousses.append(args)
                return subprocess.CompletedProcess(args, 0, "", "")
            return vrai_git(folder, *args, **kw)

        coloc.git = git_sans_push
        try:
            ok = coloc.git_core_publish(ws, ".mmi-pm", "testclient", "monprojet-core", False)
        finally:
            coloc.git = vrai_git
        assert ok, "la publication doit réussir"
        assert not (ws / ".gitignore.pre-coloc").exists(), \
            "la whitelist de ws-init n'est pas un .gitignore tiers à sauvegarder"
        assert (ws / ".gitignore").read_text(encoding="utf-8") == GITIGNORE_WS_INIT, \
            "…ni à réécrire : ses règles sont déjà les bonnes"
        assert pousses, "un push aurait dû être tenté"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted({k: v for k, v in globals().items() if k.startswith("test_")}.items()):
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {name} : {e}")
    sys.exit(1 if failed else 0)
