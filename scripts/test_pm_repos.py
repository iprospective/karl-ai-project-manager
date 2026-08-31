#!/usr/bin/env python3
"""Tests RM2838 — `repos[].remotes` : transport vs identité, et rattachement.

Un remote a deux propriétés que rien ne déduit l'une de l'autre : le TRANSPORT
(l'alias SSH, qui porte port et clé) et l'IDENTITÉ (l'URL canonique, seule à
rattacher le dépôt à une instance du registre). Le contrat ne portait que le
premier. Ces tests verrouillent la forme riche `{url, ssh}` ET, surtout, le fait
qu'une CHAÎNE se comporte exactement comme avant — 46 entrées `repos[]` en place.

100 % hors ligne : registre fictif injecté dans pm_forge, aucun accès réseau.

Lancer : python3 scripts/test_pm_repos.py
"""
import contextlib
import importlib.util
import io
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_forge                                                     # noqa: E402
import pm_repos                                                     # noqa: E402
from pm_registry import Registry                                    # noqa: E402

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


REG = Registry.from_config({
    "defaults": {"forge": "gitlab-ipro"},
    "servers": {
        "gitlab-ipro": {"axis": "forge", "type": "gitlab",
                        "url": "https://gitlab.example.test",
                        "ssh_aliases": ["gitlab"]},
        "gogs-alpha":  {"axis": "forge", "type": "gogs",
                        "url": "https://gogs.alpha.test",
                        "ssh_aliases": ["alpha-tools"]},
    },
})
pm_forge.set_registry(REG)

# ── 1. Forme des remotes ────────────────────────────────────────────────────

check("chaîne : transport = la chaîne, identité inconnue",
      pm_repos.remote_spec("gitlab:o/r.git") == ("gitlab:o/r.git", ""))
check("mapping {url, ssh} : ssh est le transport, url l'identité",
      pm_repos.remote_spec({"url": "https://gogs.alpha.test/o/r.git",
                            "ssh": "ssh://gogs@alpha-tools/o/r.git"})
      == ("ssh://gogs@alpha-tools/o/r.git", "https://gogs.alpha.test/o/r.git"))
check("mapping {url} seul : l'URL sert aussi de transport",
      pm_repos.remote_spec({"url": "https://gogs.alpha.test/o/r.git"})
      == ("https://gogs.alpha.test/o/r.git", "https://gogs.alpha.test/o/r.git"))
check("mapping {ssh} seul : transport, identité inconnue",
      pm_repos.remote_spec({"ssh": "gitlab:o/r.git"}) == ("gitlab:o/r.git", ""))


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except pm_repos.RepoConfError:
        return True
    return False


check("mapping vide : refusé", raises(pm_repos.remote_spec, {}))
check("mapping ni url ni ssh : refusé",
      raises(pm_repos.remote_spec, {"url": "", "ssh": ""}))
check("clé inconnue : refusée (un `shh:` passerait pour « pas de transport »)",
      raises(pm_repos.remote_spec, {"shh": "x"}))
check("chaîne vide : refusée", raises(pm_repos.remote_spec, ""))
check("None : refusé", raises(pm_repos.remote_spec, None))
check("type inattendu : refusé", raises(pm_repos.remote_spec, ["a"]))

check("validate_remotes : manifeste historique accepté",
      pm_repos.validate_remotes({"name": "r", "remotes": {"origin": "gitlab:o/r.git"}}))
check("validate_remotes : forme riche acceptée",
      pm_repos.validate_remotes({"name": "r", "remotes": {
          "origin": {"url": "https://gitlab.example.test/o/r.git", "ssh": "gitlab:o/r.git"}}}))
check("validate_remotes : remotes non-mapping refusé",
      raises(pm_repos.validate_remotes, {"name": "r", "remotes": ["x"]}))

# ── 2. Rattachement, par ordre de sûreté ────────────────────────────────────

RICH = {"name": "matnat_sf7", "instance": "gogs-alpha",
        "remotes": {"origin": {"url": "https://gogs.alpha.test/o/r.git",
                               "ssh": "ssh://gogs@alpha-tools/o/r.git"}}}

inst, how = pm_repos.repo_instance(RICH)
check("rattachement 1 : `instance:` explicite gagne",
      inst.name == "gogs-alpha" and how.startswith("instance:"))

BY_URL = {"name": "r", "remotes": {"origin": {
    "url": "https://gogs.alpha.test/o/r.git", "ssh": "ssh://gogs@inconnu-xyz/o/r.git"}}}
inst, how = pm_repos.repo_instance(BY_URL)
check("rattachement 2 : à défaut, l'URL canonique",
      inst.name == "gogs-alpha" and how.startswith("url →"))

BY_ALIAS = {"name": "r", "remotes": {"origin": "ssh://gogs@alpha-tools/o/r.git"}}
inst, how = pm_repos.repo_instance(BY_ALIAS)
check("rattachement 3 : à défaut, l'alias SSH du transport",
      inst.name == "gogs-alpha" and how.startswith("alias →"))

inst, how = pm_repos.repo_instance({"name": "r", "remotes": {"origin": "ssh://x@nulle-part/o/r.git"}})
check("rattachement impossible : DÉCLARÉ inconnu, jamais deviné",
      inst is None and how == "inconnu")

inst, how = pm_repos.repo_instance({"name": "r", "instance": "n-existe-pas",
                                    "remotes": {"origin": "gitlab:o/r.git"}})
check("instance déclarée absente du registre : dit, pas contourné",
      inst is None and "absente du registre" in how)

inst, how = pm_repos.repo_instance({"name": "r", "remotes": {}})
check("pas de remote origin : dit", inst is None and "pas de remote" in how)

# ── 3. Incohérences détectées (garde pm-doctor) ─────────────────────────────

check("conf saine : aucun conflit", pm_repos.remote_conflicts(RICH) == [])

CROSS = {"name": "r", "remotes": {"origin": {
    "url": "https://gitlab.example.test/o/r.git",       # GitLab
    "ssh": "ssh://gogs@alpha-tools/o/r.git"}}}          # …mais transport Gogs
msgs = pm_repos.remote_conflicts(CROSS)
check("URL et transport sur DEUX forges : signalé",
      any("deux forges différentes" in m for m in msgs))

UNKNOWN_HOST = {"name": "r", "remotes": {"origin": {"url": "https://nulle-part.test/o/r.git"}}}
check("URL vers un hôte qu'aucune instance ne sert : signalé",
      any("qu'aucune instance du registre ne sert" in m
          for m in pm_repos.remote_conflicts(UNKNOWN_HOST)))

MISDECLARED = {"name": "r", "instance": "gitlab-ipro",
               "remotes": {"origin": {"url": "https://gogs.alpha.test/o/r.git"}}}
check("instance déclarée ≠ instance de l'URL : signalé",
      any("mais l'URL désigne gogs-alpha" in m
          for m in pm_repos.remote_conflicts(MISDECLARED)))

check("chaîne historique cohérente : aucun bruit",
      pm_repos.remote_conflicts({"name": "r", "remotes": {"origin": "gitlab:o/r.git"}}) == [])

# ── 4. Backfill : l'identité déclarée survit à une migration ────────────────

check("merge_remote : une chaîne reste le transport constaté",
      pm_repos.merge_remote("gitlab:o/r.git", "gitlab:o/r-new.git") == "gitlab:o/r-new.git")
check("merge_remote : l'URL déclarée est préservée, le ssh recalé",
      pm_repos.merge_remote({"url": "https://gogs.alpha.test/o/r.git",
                             "ssh": "vieux"}, "ssh://gogs@alpha-tools/o/r.git")
      == {"url": "https://gogs.alpha.test/o/r.git",
          "ssh": "ssh://gogs@alpha-tools/o/r.git"})
check("merge_remote : transport identique à l'URL → pas de ssh redondant",
      pm_repos.merge_remote({"url": "https://gogs.alpha.test/o/r.git"},
                            "https://gogs.alpha.test/o/r.git")
      == {"url": "https://gogs.alpha.test/o/r.git"})

merged = pm_repos.merge_entry(
    RICH,
    {"name": "matnat_sf7", "remotes": {"origin": "ssh://gogs@alpha-tools/o/r.git"},
     "integration_branch": "dev"})
check("merge_entry : `instance:` déclaré survit au backfill",
      merged.get("instance") == "gogs-alpha")
check("merge_entry : l'URL canonique survit au backfill",
      merged["remotes"]["origin"]["url"] == "https://gogs.alpha.test/o/r.git")
check("merge_entry : le constat met bien à jour ce qu'il connaît",
      merged["integration_branch"] == "dev")
check("merge_entry : sans entrée préalable, le constat passe tel quel",
      pm_repos.merge_entry(None, {"name": "x", "remotes": {"origin": "a"}})
      == {"name": "x", "remotes": {"origin": "a"}})

# ── 5. pm-env-init : c'est bien le TRANSPORT qui part à git ─────────────────

spec = importlib.util.spec_from_file_location("pm_env_init", HERE / "pm-env-init.py")
env_init = importlib.util.module_from_spec(spec)
spec.loader.exec_module(env_init)


def announced(repo):
    """Actions annoncées par ensure_bare en dry-run (aucune mutation)."""
    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(buf):
        env_init.ensure_bare(env_init.Ctx(dry=True, verbose=False),
                             pathlib.Path(d), repo)
    return buf.getvalue()


out = announced({"name": "r", "remotes": {
    "origin": {"url": "https://gogs.alpha.test/o/r.git",
               "ssh": "ssh://gogs@alpha-tools/o/r.git"}}})
check("env-init : git remote add reçoit le ssh, pas l'url",
      "git remote add origin ssh://gogs@alpha-tools/o/r.git" in out
      and "https://gogs.alpha.test/o/r.git" not in out)

out = announced({"name": "r", "remotes": {"origin": {"url": "https://gogs.alpha.test/o/r.git"}}})
check("env-init : sans ssh, l'url sert de transport",
      "git remote add origin https://gogs.alpha.test/o/r.git" in out)

out = announced({"name": "r", "remotes": {"origin": "gitlab:o/r.git", "upstream": "gitlab:u/r.git"}})
check("env-init : chaînes historiques inchangées, origin d'abord",
      "git remote add origin gitlab:o/r.git" in out
      and "git remote add upstream gitlab:u/r.git" in out
      and out.index("origin gitlab") < out.index("upstream gitlab"))

# La validation du manifeste refuse une conf malformée AVANT toute mutation.
with tempfile.TemporaryDirectory() as d:
    ws = pathlib.Path(d)
    (ws / ".mmi-pm").mkdir()
    meta = ws / ".mmi-pm" / "meta.yml"
    meta.write_text("repos:\n- name: r\n  remotes:\n    origin: {shh: x}\n", encoding="utf-8")
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            env_init.load_repos(ws)
        ok = False
    except SystemExit as e:
        ok = "clé(s) inconnue(s) shh" in (err.getvalue() + str(e))
    check("env-init : manifeste malformé refusé avant d'instancier", ok)

    meta.write_text("repos:\n- name: r\n  remotes:\n"
                    "    origin: {url: https://gitlab.example.test/o/r.git, ssh: 'gitlab:o/r.git'}\n"
                    "  integration_branch: dev\n", encoding="utf-8")
    check("env-init : manifeste en forme riche accepté",
          env_init.load_repos(ws)[0]["name"] == "r")

    meta.write_text("repos:\n- name: r\n  remotes: {origin: 'gitlab:o/r.git'}\n"
                    "  integration_branch: dev\n", encoding="utf-8")
    check("env-init : manifeste historique toujours accepté",
          env_init.load_repos(ws)[0]["remotes"]["origin"] == "gitlab:o/r.git")

# ── 6. Sans registre : rien ne se rattache, et rien ne casse ────────────────

pm_forge.set_registry(None)
inst, how = pm_repos.repo_instance(RICH)
check("sans registre : rattachement inconnu, pas d'exception", inst is None)
check("sans registre : aucun conflit inventé", pm_repos.remote_conflicts(CROSS) == [])
check("sans registre : la forme des remotes reste validée",
      pm_repos.remote_transport({"ssh": "gitlab:o/r.git"}) == "gitlab:o/r.git")
pm_forge.set_registry(REG)

# ── 7. Bout en bout : un vrai bare reçoit bien le transport ─────────────────

with tempfile.TemporaryDirectory() as d:
    ws = pathlib.Path(d)
    src = ws / "src.git"
    subprocess.run(["git", "init", "--bare", "-q", str(src)], check=True)
    repo = {"name": "r", "remotes": {"origin": {"url": "https://gogs.alpha.test/o/r.git",
                                                "ssh": str(src)}}}
    with contextlib.redirect_stdout(io.StringIO()):
        env_init.ensure_bare(env_init.Ctx(dry=False, verbose=False), ws, repo)
    got = subprocess.run(["git", "-C", str(ws / "repos" / "r.git"),
                          "remote", "get-url", "origin"],
                         capture_output=True, text=True).stdout.strip()
    check("bout en bout : le remote git porte le transport", got == str(src))

pm_forge.set_registry(None)

if fails:
    print(f"\n✗ {len(fails)} échec(s)")
    raise SystemExit(1)
print("\nOK — remotes {url, ssh} et rattachement (RM2838)")
