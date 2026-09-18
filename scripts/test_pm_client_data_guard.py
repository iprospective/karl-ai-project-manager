#!/usr/bin/env python3
"""Tests RM3201 — aucune donnée client dans un dépôt publiable.

Ce qui est protégé, dans l'ordre d'importance :

  1. **les motifs viennent des données privées, et d'elles seules** : un client
     (`type: client`) est un motif, un produit ou soi-même non ; un webmail grand
     public ou le domaine maison n'est jamais un domaine client ;
  2. **rien ne passe entre les mailles connues de RM3200** : casse, accents, slug
     collé par `_` ou `-`, point échappé dans une regex, sous-domaine ;
  3. **seules les lignes AJOUTÉES sont jugées au commit** : une dette existante ne
     bloque pas chaque commit qui touche le fichier ;
  4. **un dépôt non déclaré publiable n'est pas contrôlé** — les dépôts clients
     nomment leur client, c'est leur objet ;
  5. **un slug qui est aussi un mot courant** n'est signalé qu'en identifiant.

Toutes les données ici sont FICTIVES (société « Zorglub ») : un test du garde-fou
qui contiendrait un vrai client serait la fuite qu'il doit empêcher.

Lancer : python3 scripts/test_pm_client_data_guard.py
"""
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import yaml  # noqa: E402

import pm_client_data_guard as G  # noqa: E402
import pm_paths  # noqa: E402
from pm_paths import PMConfig  # noqa: E402

REAL_CONFIG = SCRIPTS.parent / "pm.config.yml"
COMMON = ["bonjour", "site"]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, str(SCRIPTS / filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _w(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity(clients: Path, slug, typ, name):
    _w(clients / slug / "meta.yml", yaml.safe_dump({"slug": slug, "name": name, "type": typ}))
    _w(clients / slug / "client" / "overview.md", "# vue\n")


def make_tree(tmp: Path) -> PMConfig:
    pm_dir, projects = tmp / "pm", tmp / "projects"
    pm_dir.mkdir()
    cfg = yaml.safe_load(REAL_CONFIG.read_text(encoding="utf-8"))
    cfg["roots"] = {"pm_dir": str(pm_dir), "projects_root": str(projects),
                    "state_dir": str(tmp / "var"), "conf_dir": str(pm_dir),
                    "log_dir": str(tmp / "var" / "log")}
    _w(pm_dir / "pm.config.yml", yaml.safe_dump(cfg, allow_unicode=True))
    clients = projects / "clients"
    _entity(clients, "zorglub", "client", "Zorglub Industries")
    _entity(clients, "bonjour", "client", "Bonjour")          # slug = mot courant
    _entity(clients, "acme", "product", "Acme Produit")       # un produit : publiable
    _entity(clients, "iprospective", "self", "iProspective")  # soi-même : publiable
    site = clients / "zorglub" / "projects" / "site"
    _w(site / "meta.yml", yaml.safe_dump({"slug": "site", "type": "client"}))
    _w(site / "project" / "overview.md", "# site\n")
    _w(site / "project" / "environments.md",
       "---\nenvironments:\n  - name: prod\n    url: https://erp.zorglub-industries.fr\n"
       "    host: srv-prd.zorglub-hosting.com\n    notes: \"IP 93.184.216.34, backup "
       "10.0.3.5, lxc dev.zorglub.lxc, PrestaShop 1.7.8.11\"\n---\n"
       # du texte technique qui a la FORME d'hôtes et d'adresses (faux positifs réels) :
       "python -c 'import sys,json; json.load(sys.stdin)' ; git clone depot.git ;\n"
       "remote https://github.com/zorglub/app ; api.github.com ; admin@dev.lxc\n")
    pm_ai = clients / "iprospective" / "projects" / "pm-ai-agents"
    _w(pm_ai / "project" / "overview.md", "# pm\n")
    _w(pm_ai / "contacts" / "zoe-tartempion.yml", yaml.safe_dump(
        {"ref": "zoe-tartempion", "first_name": "Zoé", "last_name": "Tartempion",
         "emails": ["zoe@zorglub-industries.fr"], "internal": False}, allow_unicode=True))
    _w(pm_ai / "contacts" / "moi.yml", yaml.safe_dump(
        {"ref": "moi", "first_name": "Jean", "last_name": "Maison",
         "emails": ["jean@iprospective.fr"], "internal": True}))
    c = PMConfig.load(pm_dir)
    os.environ.pop("REDMINE_CF_PARTNER_ISSUE_ID", None)
    # là où la conf la place (var/ depuis RM3200) : le test ne présume pas de l'emplacement
    _w(Path(c.path("mail_routing_file")), yaml.safe_dump(
        {"addresses": {"contact.zorglub@gmail.com": "zorglub"},
         "domains": {"zorglub-shop.fr": "zorglub"}}))
    return c


def git(repo: Path, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env={**os.environ, "GIT_AUTHOR_NAME": "t",
                                           "GIT_AUTHOR_EMAIL": "t@t.example",
                                           "GIT_COMMITTER_NAME": "t",
                                           "GIT_COMMITTER_EMAIL": "t@t.example"})


def make_repo(tmp: Path, guard=True) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "core.hooksPath", "/dev/null")      # aucun hook réel pendant le test
    if guard:
        _w(repo / G.GUARD_FILE, yaml.safe_dump({"exempt": ["docs/histo/*"],
                                                 "common_words": COMMON}))
    _w(repo / "notes.md", "ligne 1\nancienne mention zorglub\n")   # dette existante
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    return repo


# ── 1. collecte ──────────────────────────────────────────────────────────────

def test_collect_takes_clients_only():
    with tempfile.TemporaryDirectory() as d:
        p = G.collect(make_tree(Path(d)), COMMON)
        assert "zorglub" in p.slugs and "bonjour" in p.common_slugs
        assert "acme" not in p.slugs | p.common_slugs, "un produit n'est pas un client"
        assert "iprospective" not in p.slugs | p.common_slugs, "soi-même n'est pas un client"


def test_collect_names_hosts_emails_ips():
    with tempfile.TemporaryDirectory() as d:
        p = G.collect(make_tree(Path(d)), COMMON)
        assert "zorglub industries" in p.names and "zoe tartempion" in p.names
        assert "jean maison" not in p.names, "un contact interne n'est pas un motif"
        for h in ("erp.zorglub-industries.fr", "zorglub-industries.fr",
                  "srv-prd.zorglub-hosting.com", "zorglub-hosting.com", "zorglub-shop.fr"):
            assert h in p.hosts, h
        assert "contact.zorglub@gmail.com" in p.emails and "zoe@zorglub-industries.fr" in p.emails
        assert "93.184.216.34" in p.ips and "10.0.3.5" not in p.ips, "IP privée : pas un motif"


def test_collect_never_public_nor_own_domains():
    with tempfile.TemporaryDirectory() as d:
        p = G.collect(make_tree(Path(d)), COMMON)
        assert "gmail.com" not in p.hosts, "un webmail grand public n'identifie aucun client"
        assert not any("iprospective" in h for h in p.hosts), "le domaine maison est publiable"
        assert "jean@iprospective.fr" not in p.emails
        assert not any(h.endswith(".lxc") for h in p.hosts), "un nom interne n'est pas public"


def test_collect_ignores_code_versions_and_platforms():
    """Faux positifs rencontrés au premier audit réel (RM3201)."""
    with tempfile.TemporaryDirectory() as d:
        p = G.collect(make_tree(Path(d)), COMMON)
        for h in ("sys.stdin", "json.load", "depot.git", "github.com", "api.github.com"):
            assert h not in p.hosts, h
        assert "1.7.8.11" not in p.ips, "une version n'est pas une IP"
        assert "admin@dev.lxc" not in p.emails, "une adresse interne n'est pas publique"


def test_collect_empty_without_private_data():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "pm").mkdir()
        cfg = yaml.safe_load(REAL_CONFIG.read_text(encoding="utf-8"))
        cfg["roots"] = {"pm_dir": str(tmp / "pm"), "projects_root": str(tmp / "rien"),
                        "state_dir": str(tmp / "var"), "conf_dir": str(tmp / "pm")}
        _w(tmp / "pm" / "pm.config.yml", yaml.safe_dump(cfg))
        (tmp / "rien").mkdir()
        assert G.collect(PMConfig.load(tmp / "pm"), COMMON).empty()


# ── 2. détection ─────────────────────────────────────────────────────────────

def _kinds(p, line):
    return [k for k, _ in p.scan(line)]


def test_scan_catches_the_rm3200_escapes():
    with tempfile.TemporaryDirectory() as d:
        p = G.collect(make_tree(Path(d)), COMMON)
        assert _kinds(p, "déployé chez Zorglub hier") == ["client"]
        assert _kinds(p, "compte php_zorglub@prod") == ["client"], "slug collé par underscore"
        assert _kinds(p, "Chantier Zörglub !") == ["client"], "accent"
        assert _kinds(p, "ZORGLUB-presta") == ["client"], "majuscules, tiret"
        assert _kinds(p, "un zorglubien") == [], "pas un mot entier"
        assert _kinds(p, r"/srv-prd\.zorglub-hosting\.com/") == ["domaine"], "point échappé"
        assert _kinds(p, "https://www.zorglub-industries.fr/x") == ["domaine"], "sous-domaine"
        assert _kinds(p, "IP 93.184.216.34") == ["ip"] and _kinds(p, "v93.184.216.345") == []


def test_scan_reports_the_most_specific_once():
    with tempfile.TemporaryDirectory() as d:
        p = G.collect(make_tree(Path(d)), COMMON)
        assert _kinds(p, "écrire à zoe@zorglub-industries.fr") == ["adresse"]
        assert _kinds(p, "Zoé Tartempion a validé") == ["nom"]
        assert _kinds(p, "contact.zorglub@gmail.com") == ["adresse"]
        assert _kinds(p, "quelqu.un@gmail.com") == [], "gmail seul ne dit rien"


def test_scan_common_word_slug_only_as_identifier():
    with tempfile.TemporaryDirectory() as d:
        p = G.collect(make_tree(Path(d)), COMMON)
        assert _kinds(p, "Bonjour à tous, bonjour.") == [], "en prose : un mot, pas un client"
        assert _kinds(p, "clients/bonjour/infra") == ["client"]
        assert _kinds(p, "user php_bonjour") == ["client"]
        assert _kinds(p, "le `bonjour-presta`") == ["client"]


def test_scan_fictional_set_and_allow_marker_pass():
    with tempfile.TemporaryDirectory() as d:
        p = G.collect(make_tree(Path(d)), COMMON)
        assert _kinds(p, "clienta.example, erp.clientb.example, acme") == []
        assert _kinds(p, "zorglub  # client-data-guard: allow — conf active, RMxxxx") == []


# ── 3. au commit : les lignes ajoutées seules ────────────────────────────────

def test_staged_judges_added_lines_only():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = G.collect(make_tree(tmp), COMMON)
        repo = make_repo(tmp)
        _w(repo / "notes.md", "ligne 1\nancienne mention zorglub\nnouvelle : erp.zorglub-industries.fr\n")
        _w(repo / "docs" / "histo" / "vieux.md", "zorglub partout\n")      # exempté
        git(repo, "add", "notes.md", "docs/histo/vieux.md")
        f = G.check_staged(repo, p, ["docs/histo/*"])
        assert [(x.path, x.line, x.kind) for x in f] == [("notes.md", 3, "domaine")], f


def test_guard_file_itself_is_not_checked():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = G.collect(make_tree(tmp), COMMON)
        repo = make_repo(tmp)
        _w(repo / G.GUARD_FILE, yaml.safe_dump({"common_words": COMMON + ["zorglub"]}))
        git(repo, "add", G.GUARD_FILE)
        assert G.check_staged(repo, p, []) == []


def test_tree_audit_sees_existing_debt():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = G.collect(make_tree(tmp), COMMON)
        f = G.check_tree(make_repo(tmp), p)
        assert [(x.path, x.line) for x in f] == [("notes.md", 2)]


def test_history_sees_deleted_files_and_messages():
    """Un miroir publie l'historique : un fichier supprimé et un message de commit comptent."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = G.collect(make_tree(tmp), COMMON)
        repo = make_repo(tmp)
        (repo / "notes.md").unlink()
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "retire la note de zoe@zorglub-industries.fr")
        assert G.check_tree(repo, p) == [], "le HEAD est propre…"
        f = G.check_history(repo, p)
        kinds = sorted((x.path.split("@")[0].split()[0], x.kind) for x in f)
        assert ("notes.md", "client") in kinds, "…mais la version supprimée reste publiée"
        assert ("commit", "adresse") in kinds, "…et le message de commit aussi"


# ── 4. le hook ───────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _patched_load(cfg):
    orig = pm_paths.PMConfig.load
    pm_paths.PMConfig.load = classmethod(lambda cls, pm_dir=None: cfg)
    try:
        yield
    finally:
        pm_paths.PMConfig.load = orig


def _hook_check(repo, cfg, env=None):
    hook = _load("pm_pre_commit_t", "pm-pre-commit.py")
    err = io.StringIO()
    old = {k: os.environ.get(k) for k in (env or {})}
    os.environ.update(env or {})
    try:
        with _patched_load(cfg), contextlib.redirect_stderr(err):
            rc = hook.client_data_check(repo)
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    return rc, err.getvalue()


def test_hook_refuses_on_publishable_repo():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg = make_tree(tmp)
        repo = make_repo(tmp)
        _w(repo / "a.md", "voir zoe@zorglub-industries.fr\n")
        git(repo, "add", "a.md")
        rc, err = _hook_check(repo, cfg)
        assert rc == 1 and "REFUS" in err and "a.md:1: [adresse]" in err, err


def test_hook_ignores_repo_not_declared_publishable():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg = make_tree(tmp)
        repo = make_repo(tmp, guard=False)
        _w(repo / "a.md", "chez zorglub\n")
        git(repo, "add", "a.md")
        assert _hook_check(repo, cfg) == (0, ""), "un dépôt client nomme son client"


def test_hook_skip_is_loud():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg = make_tree(tmp)
        repo = make_repo(tmp)
        _w(repo / "a.md", "chez zorglub\n")
        git(repo, "add", "a.md")
        rc, err = _hook_check(repo, cfg, {"PM_SKIP_CLIENT_DATA_CHECK": "1"})
        assert rc == 0 and "DÉSACTIVÉ" in err


def test_hook_without_private_data_warns_and_passes():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg = make_tree(tmp)
        repo = make_repo(tmp)
        orig = G.collect
        G.collect = lambda cfg, common=(): G.Patterns()
        try:
            rc, err = _hook_check(repo, cfg)
        finally:
            G.collect = orig
        assert rc == 0 and "NON contrôlées" in err


# ── 5. le CLI ────────────────────────────────────────────────────────────────

def test_cli_patterns_never_prints_values():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg = make_tree(tmp)
        repo = make_repo(tmp)
        cli = _load("pm_check_t", "pm-check-no-client-data.py")
        out = io.StringIO()
        with _patched_load(cfg), contextlib.redirect_stdout(out):
            rc = cli.main(["--patterns", "--repo", str(repo)])
        assert rc == 0 and "slugs" in out.getvalue()
        assert "zorglub" not in out.getvalue().lower(), "les motifs SONT les données"


def test_cli_all_exit_codes():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg = make_tree(tmp)
        repo = make_repo(tmp)
        cli = _load("pm_check_t2", "pm-check-no-client-data.py")
        with _patched_load(cfg), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            assert cli.main(["--all", "--repo", str(repo)]) == 1
            (repo / G.GUARD_FILE).unlink()
            assert cli.main(["--all", "--repo", str(repo)]) == 0, "non publiable : rien à dire"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    ok = 0
    for name, fn in tests:
        try:
            fn()
            ok += 1
            print(f"  ✓ {name}")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {name} — {e!r}")
    print(f"\n{ok}/{len(tests)} ok")
    sys.exit(0 if ok == len(tests) else 1)
