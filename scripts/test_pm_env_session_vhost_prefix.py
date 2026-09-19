#!/usr/bin/env python3
"""Tests RM3247 — préfixe de vhost paramétrable par repo (`runtime.vhost_prefix`).

Le besoin : le vhost d'un env de ticket portait toujours le nom du REPO. Pour un repo au nom
générique (`dolibarr`, partagé par tous les clients qui en ont un), l'URL ne disait plus de
quel client il s'agissait : `dolibarr-rm12.lxc` là où l'on attendait `client-a-erp-rm12.lxc`.

Ce qui est protégé ici :
  1. SANS préfixe, rien ne change — mêmes noms qu'avant, y compris pour un nom de repo qui
     ne serait pas un label DNS valide (`legacy_repo`) : ce qui marchait doit marcher ;
  2. AVEC préfixe, tout ce qui se VOIT le suit : vhost, URL, test_url, {host} ;
  3. le DOSSIER ne change pas, et le canari garde son nom — il prouve « ce vhost sert CE
     worktree », et le cockpit le compare au nom du dossier ;
  4. `teardown` retire le vhost sous le nom que `create` a posé — sinon il reste orphelin ;
  5. un préfixe invalide est REFUSÉ plutôt que transmis au helper privilégié ;
  6. le cockpit sonde l'hôte réellement servi (celui de test_url), pas `<dossier>.lxc`.

Lancement : python3 scripts/test_pm_env_session_vhost_prefix.py
"""
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("pm_env_session", HERE / "pm-env-session.py")
pes = importlib.util.module_from_spec(_spec)
sys.modules["pm_env_session"] = pes
_spec.loader.exec_module(pes)

FAILURES = []


def check(label, got, want):
    if got == want:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label} : attendu {want!r}, obtenu {got!r}")
        FAILURES.append(label)


def git(*a, cwd=None):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


def build_ws(tmp, runtime_yaml):
    """Workspace RM1993 minimal : manifeste avec runtime, bare, un commit sur main."""
    ws = tmp / "ws"
    (ws / ".mmi-pm").mkdir(parents=True)
    (ws / ".mmi-pm" / "meta.yml").write_text(
        "repos:\n- name: dolibarr\n  integration_branch: main\n" + runtime_yaml, encoding="utf-8")
    (ws / "envs").mkdir()
    bare = ws / "repos" / "dolibarr.git"
    bare.parent.mkdir()
    git("init", "-q", "--bare", str(bare))
    seed = tmp / "seed"
    git("clone", "-q", str(bare), str(seed))
    git("config", "user.email", "t@t", cwd=seed)
    git("config", "user.name", "t", cwd=seed)
    (seed / "htdocs").mkdir()
    (seed / "htdocs" / "index.php").write_text("<?php\n")
    git("add", "-A", cwd=seed)
    git("commit", "-qm", "seed", cwd=seed)
    git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=seed)
    return ws


def run(cmd, ws, rmid=3040):
    """Joue create|teardown en dry-run ; rend (sortie, appels au helper, test_url posé)."""
    appels, urls = [], []
    sauve = (pes.load_env_runtime_cfg, pes.helper, pes.set_test_url)
    pes.load_env_runtime_cfg = lambda: {"workspace_map": {str(ws): str(ws)}, "ssh_host": "x", "helper": "h"}
    pes.helper = lambda cfg, args, dry, **k: appels.append(list(args))
    pes.set_test_url = lambda ws_, rid, url, dry: urls.append(url)

    class Args:
        rmid, workspace, repo = 3040, str(ws), None
        dry_run, force, keep_db = True, False, False
        slug, db_clone, no_db_clone, no_vhost = "lot", False, True, False
    Args.rmid = rmid
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            (pes.cmd_create if cmd == "create" else pes.cmd_teardown)(Args())
    finally:
        pes.load_env_runtime_cfg, pes.helper, pes.set_test_url = sauve
    return buf.getvalue(), appels, urls


RUNTIME_PREFIXE = """  runtime:
    pool: pool-a
    docroot: htdocs
    vhost_prefix: client-a-erp
    post_create:
      - "echo url={host} dossier={env}"
"""
RUNTIME_SANS = """  runtime:
    pool: pool-a
    docroot: htdocs
    post_create:
      - "echo url={host} dossier={env}"
"""


def test_vhost_name():
    print("vhost_name (pur) :")
    check("sans runtime : nom du repo", pes.vhost_name({"name": "dolibarr"}, 3040), "dolibarr-rm3040")
    check("runtime sans préfixe : nom du repo",
          pes.vhost_name({"name": "dolibarr", "runtime": {"pool": "p"}}, 3040), "dolibarr-rm3040")
    check("préfixe vide : nom du repo",
          pes.vhost_name({"name": "dolibarr", "runtime": {"vhost_prefix": "  "}}, 3040), "dolibarr-rm3040")
    check("préfixe posé : il gagne",
          pes.vhost_name({"name": "dolibarr", "runtime": {"vhost_prefix": "client-a-erp"}}, 3040),
          "client-a-erp-rm3040")
    # Le défaut n'est PAS validé : un nom de repo historique hors label DNS continue de marcher
    check("nom de repo historique non validé (rien ne casse)",
          pes.vhost_name({"name": "legacy_repo"}, 12), "legacy_repo-rm12")
    for mauvais in ("ClientA", "client_a_erp", "-client-a", "client-a-", "a b", "x" * 49, "client.a"):
        try:
            pes.vhost_name({"name": "d", "runtime": {"vhost_prefix": mauvais}}, 1)
            refuse = False
        except SystemExit:
            refuse = True
        check(f"préfixe invalide refusé : {mauvais[:12]!r}", refuse, True)


def test_create_avec_prefixe():
    print("create (dry-run) avec vhost_prefix :")
    with tempfile.TemporaryDirectory() as t:
        ws = build_ws(Path(t), RUNTIME_PREFIXE)
        out, appels, urls = run("create", ws)
        vh = [a for a in appels if a[0] == "vhost-add"]
        check("vhost posé sous le nom préfixé", vh[0][1] if vh else None, "client-a-erp-rm3040")
        check("test_url suit le préfixe", urls, ["http://client-a-erp-rm3040.lxc/"])
        check("{host} substitué dans post_create",
              "url=client-a-erp-rm3040.lxc dossier=dolibarr-rm3040" in out, True)
        check("le DOSSIER garde le nom du repo", "envs/dolibarr-rm3040" in out, True)
        check("le récapitulatif annonce l'URL servie", "http://client-a-erp-rm3040.lxc/" in out, True)


def test_create_sans_prefixe():
    print("create (dry-run) sans préfixe — comportement historique :")
    with tempfile.TemporaryDirectory() as t:
        ws = build_ws(Path(t), RUNTIME_SANS)
        out, appels, urls = run("create", ws)
        vh = [a for a in appels if a[0] == "vhost-add"]
        check("vhost au nom du repo", vh[0][1] if vh else None, "dolibarr-rm3040")
        check("test_url inchangé", urls, ["http://dolibarr-rm3040.lxc/"])
        check("{host} = <repo>-rm<id>.lxc", "url=dolibarr-rm3040.lxc dossier=dolibarr-rm3040" in out, True)


def test_teardown_retire_le_bon_vhost():
    print("teardown (dry-run) :")
    with tempfile.TemporaryDirectory() as t:
        ws = build_ws(Path(t), RUNTIME_PREFIXE)
        _, appels, _ = run("teardown", ws)
        rm = [a for a in appels if a[0] == "vhost-remove"]
        check("vhost retiré sous le nom que create a posé", rm[0][1] if rm else None, "client-a-erp-rm3040")


def test_cockpit_sonde_l_hote_servi():
    print("cockpit — hôte sondé :")
    tmp = tempfile.mkdtemp(prefix="karl-rm3247-")
    os.environ.setdefault("KARL_AGENT_PROJECTS_BASE", str(Path(tmp) / "clients"))
    os.environ.setdefault("KARL_JOURNAL_DIR", tmp)
    os.environ.setdefault("KARL_JOURNAL_STDERR", "0")
    spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
    ka = importlib.util.module_from_spec(spec)
    sys.modules["karl_agent"] = ka
    spec.loader.exec_module(ka)
    check("test_url .lxc préfixé : c'est lui qu'on sonde",
          ka._env_test_host("dolibarr-rm3040", "http://client-a-erp-rm3040.lxc/"), "client-a-erp-rm3040.lxc")
    check("sans test_url : <dossier>.lxc (historique)",
          ka._env_test_host("dolibarr-rm3040", None), "dolibarr-rm3040.lxc")
    check("test_url hors .lxc (préprod distante) : ignoré",
          ka._env_test_host("shop-rm12", "https://preprod.client-a.example/"),
          "shop-rm12.lxc")
    check("pas d'env : rien à sonder", ka._env_test_host(None, "http://x.lxc/"), None)


if __name__ == "__main__":
    test_vhost_name()
    test_create_avec_prefixe()
    test_create_sans_prefixe()
    test_teardown_retire_le_bon_vhost()
    test_cockpit_sonde_l_hote_servi()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} échec(s) : " + ", ".join(FAILURES))
        sys.exit(1)
    print("== OK ==")
