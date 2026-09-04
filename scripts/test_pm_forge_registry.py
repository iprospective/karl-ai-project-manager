#!/usr/bin/env python3
"""Tests RM2766 — pm_forge résout ses forges par le REGISTRE, plus par variables.

Le registre (`pm.config.yml :: providers.servers`) portait déjà l'URL, le type et
les alias de chaque forge, mais `pm_forge` ne le lisait jamais : il résolvait par
GITLAB_URL / GOGS_URL / GITHUB_URL, donc une seule instance par TYPE. La
déclaration d'un projet était correctement résolue par `pm-providers`… puis
ignorée par toute opération.

100 % hors ligne : instances FICTIVES injectées par `set_registry`, aucun appel
réseau, aucune dépendance à la conf de la machine.

Lancer : python3 scripts/test_pm_forge_registry.py
"""
import importlib.util
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("pm_forge", HERE / "pm_forge.py")
pm_forge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm_forge)
from pm_registry import Registry                                    # noqa: E402

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# Registre fictif : DEUX instances gogs (multi-instance) + gitlab + github.
CFG = {
    "defaults": {"forge": "gitlab-ipro"},
    "servers": {
        "gitlab-ipro":   {"axis": "forge", "type": "gitlab",
                          "url": "https://gitlab.example.test",
                          "ssh_aliases": ["gitlab", "git"]},
        "gogs-alpha":    {"axis": "forge", "type": "gogs",
                          "url": "https://gogs.alpha.test",
                          "ssh_aliases": ["alpha-tools", "alpha-git"]},
        "gogs-beta":     {"axis": "forge", "type": "gogs",
                          "url": "https://gogs.beta.test",
                          "ssh_aliases": ["beta-tools"]},
        "github-public": {"axis": "forge", "type": "github",
                          "url": "https://github.example.test",
                          "api_url": "https://api.github.example.test"},
        # Instance d'un AUTRE axe : ne doit jamais être vue comme une forge.
        "redmine-ipro":  {"axis": "task", "type": "redmine",
                          "url": "https://tasks.example.test"},
    },
}
REG = Registry.from_config(CFG)


class Env:
    """Environnement maîtrisé : les variables globales de forge sont retirées,
    pour prouver que la résolution vient bien du registre et de rien d'autre."""

    VARS = ("GITLAB_URL", "GOGS_URL", "GITHUB_URL", "GITHUB_API_URL", "PM_FORGE")

    def __init__(self, **overrides):
        self.overrides = overrides

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in self.VARS}
        for k in self.VARS:
            os.environ.pop(k, None)
        for k, v in self.overrides.items():
            os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        return False


def with_registry(reg):
    pm_forge.set_registry(reg)


# ── 1. URL et type résolus depuis le registre ────────────────────────────────

with_registry(REG)

with Env():
    f = pm_forge.GogsForge("Materiaux-Naturels/matnat_sf7",
                           instance=REG.get("gogs-alpha"))
    check("Gogs : base = URL de l'instance, sans GOGS_URL",
          f.base == "https://gogs.alpha.test")
    check("Gogs : lien-compare construit sans variable globale",
          f.compare_url("dev", "main")
          == "https://gogs.alpha.test/Materiaux-Naturels/matnat_sf7/compare/main...dev")

    g = pm_forge.GitlabForge("g/p", instance=REG.get("gitlab-ipro"))
    check("GitLab : base = URL de l'instance", g.base == "https://gitlab.example.test")

    h = pm_forge.GithubForge("o/r", instance=REG.get("github-public"))
    check("GitHub : web et api depuis l'instance",
          h.web_base == "https://github.example.test"
          and h.api_base == "https://api.github.example.test")

# ── 2. _known_hosts apprend les hôtes du registre ───────────────────────────

with Env():
    known = pm_forge._known_hosts()
    check("known_hosts : les 2 Gogs déclarés sont connus",
          known.get("gogs.alpha.test") == "gogs" and known.get("gogs.beta.test") == "gogs")
    check("known_hosts : gitlab et github déclarés sont connus",
          known.get("gitlab.example.test") == "gitlab"
          and known.get("github.example.test") == "github")
    check("known_hosts : une instance d'un autre axe n'est pas une forge",
          "tasks.example.test" not in known)

    # Conséquence directe : une URL de PR sur une forge déclarée est acceptée.
    name, path, iid = pm_forge.parse_pr_url("https://gogs.alpha.test/o/r/pulls/12")
    check("parse_pr_url : URL du Gogs déclaré acceptée",
          (name, path, iid) == ("gogs", "o/r", 12))

# ── 3. Rattachement par alias SSH ───────────────────────────────────────────

with Env():
    check("alias : 'alpha-tools' → gogs-alpha",
          pm_forge.instance_for_hint("alpha-tools").name == "gogs-alpha")
    check("alias : 'beta-tools' → gogs-beta",
          pm_forge.instance_for_hint("beta-tools").name == "gogs-beta")
    check("alias : casse ignorée",
          pm_forge.instance_for_hint("Alpha-Tools").name == "gogs-alpha")
    check("hôte : reconnu à défaut d'alias",
          pm_forge.instance_for_hint("gogs.beta.test").name == "gogs-beta")
    check("alias inconnu : None, jamais de devinette",
          pm_forge.instance_for_hint("inconnu-xyz") is None)

    # Le vrai gain : un remote tunnelé, que forge_name() ne sait pas lire.
    check("forge_name seul ne sait pas lire 'alpha-tools'",
          pm_forge.forge_name("alpha-tools") is None)
    fg = pm_forge.get_forge(url="ssh://gogs@alpha-tools/Materiaux-Naturels/matnat_sf7.git",
                            repo="/nonexistent")
    check("get_forge : remote tunnelé résolu par l'alias",
          fg.name == "gogs" and fg.base == "https://gogs.alpha.test"
          and fg.repo_path == "Materiaux-Naturels/matnat_sf7")

# ── 4. Deux instances du même type coexistent ───────────────────────────────

with Env():
    a = pm_forge.get_forge(url="ssh://gogs@alpha-tools/o/r.git", repo="/nonexistent")
    b = pm_forge.get_forge(url="ssh://gogs@beta-tools/o/r.git", repo="/nonexistent")
    check("multi-instance : deux Gogs, deux bases distinctes",
          a.base == "https://gogs.alpha.test" and b.base == "https://gogs.beta.test")

    fa, _ = pm_forge.get_forge_from_pr_url("https://gogs.alpha.test/o/r/pulls/1")
    fb, _ = pm_forge.get_forge_from_pr_url("https://gogs.beta.test/o/r/pulls/2")
    check("multi-instance : URL de PR rattachée à la bonne instance",
          fa.base == "https://gogs.alpha.test" and fb.base == "https://gogs.beta.test")

# ── 5. Rattachement explicite par nom ou objet ──────────────────────────────

with Env():
    f1 = pm_forge.get_forge(url="https://ailleurs.test/o/r.git", repo="/nonexistent",
                            instance="gogs-beta")
    check("instance= par NOM : type et URL viennent de l'instance",
          f1.name == "gogs" and f1.base == "https://gogs.beta.test")
    f2 = pm_forge.get_forge(url="https://ailleurs.test/o/r.git", repo="/nonexistent",
                            instance=REG.get("gogs-alpha"))
    check("instance= par OBJET : idem", f2.base == "https://gogs.alpha.test")
    check("instance= nom inconnu : ignoré, pas d'exception",
          pm_forge.instance_by_name("nexiste-pas") is None)

    # `forge=` explicite reste souverain : on ne lui colle pas l'URL d'un autre type.
    f3 = pm_forge.get_forge(url="ssh://gogs@alpha-tools/o/r.git", repo="/nonexistent",
                            forge="gitlab")
    check("forge= explicite prime, et n'hérite pas de l'URL d'une instance gogs",
          f3.name == "gitlab" and f3.base == "https://gitlab.iprospective.fr")

# ── 6. Sans registre : comportement STRICTEMENT inchangé ────────────────────

with_registry(None)
with Env():
    check("sans registre : GitLab garde son défaut historique",
          pm_forge.GitlabForge("g/p").base == "https://gitlab.iprospective.fr")
    check("sans registre : Gogs sans variable → base vide, comme avant",
          pm_forge.GogsForge("o/r").base == "")
    check("sans registre : GitHub garde ses défauts",
          pm_forge.GithubForge("o/r").web_base == "https://github.com"
          and pm_forge.GithubForge("o/r").api_base == "https://api.github.com")
    known = pm_forge._known_hosts()
    check("sans registre : known_hosts = les seules variables et leurs défauts",
          set(known) == {"gitlab.iprospective.fr", "github.com"})
    check("sans registre : alias inconnu reste non résolu",
          pm_forge.instance_for_hint("alpha-tools") is None)

with Env(GOGS_URL="https://gogs.legacy.test", GITLAB_URL="https://gitlab.legacy.test"):
    check("sans registre : les variables font toujours autorité",
          pm_forge.GogsForge("o/r").base == "https://gogs.legacy.test"
          and pm_forge.GitlabForge("g/p").base == "https://gitlab.legacy.test")
    check("sans registre : known_hosts suit les variables",
          pm_forge._known_hosts().get("gogs.legacy.test") == "gogs")

# ── 7. Les variables gardent la main sur le registre en cas de conflit ─────

with_registry(REG)
with Env(GOGS_URL="https://gogs.alpha.test"):
    # Même hôte des deux côtés : la variable ne doit pas être écrasée.
    check("conflit : la variable garde la main dans known_hosts",
          pm_forge._known_hosts().get("gogs.alpha.test") == "gogs")
with Env():
    # L'instance prime sur la variable QUAND elle est explicitement retenue :
    # c'est le sens du rattachement d'un projet à une forge.
    with Env(GOGS_URL="https://gogs.variable.test"):
        f = pm_forge.GogsForge("o/r", instance=REG.get("gogs-beta"))
        check("instance retenue : prime sur GOGS_URL",
              f.base == "https://gogs.beta.test")
        check("sans instance : GOGS_URL s'applique",
              pm_forge.GogsForge("o/r").base == "https://gogs.variable.test")

# ── 7 bis. Hors contexte PM : dégradation SILENCIEUSE ──────────────────────

# `PMConfig.load()` diagnostique l'absence de conf en écrivant sur stderr PUIS
# en appelant sys.exit() — que `except Exception` ne rattrape pas (SystemExit
# n'en hérite pas). Sans traitement, tout appelant hors contexte PM mourait, ou
# voyait passer une erreur qui n'en est pas une.
import contextlib                                                   # noqa: E402
import io                                                           # noqa: E402


def _reload_registry_without_pm_config():
    """Force un rechargement paresseux avec un PMConfig.load() qui sys.exit()."""
    import pm_paths
    saved = pm_paths.PMConfig.load
    pm_forge._REGISTRY, pm_forge._REGISTRY_LOADED = None, False
    err = io.StringIO()

    def _boom():
        sys.stderr.write("ERREUR : aucun .env trouvé pour …\n")
        raise SystemExit(1)

    pm_paths.PMConfig.load = staticmethod(_boom)
    try:
        with contextlib.redirect_stderr(err):
            reg = pm_forge._registry()
    finally:
        pm_paths.PMConfig.load = saved
    return reg, err.getvalue()


with Env():
    reg, err = _reload_registry_without_pm_config()
    check("hors PM : registre None, pas de SystemExit propagé", reg is None)
    check("hors PM : rien n'est écrit sur stderr", err == "")
    check("hors PM : les défauts historiques s'appliquent",
          pm_forge.GitlabForge("g/p").base == "https://gitlab.iprospective.fr")

with_registry(REG)

# ── 7 ter. Le core canonique fait foi (PM_CORE_DIR) ────────────────────────

# Depuis un clone de dev, la conf qui fait foi est celle du core, désignée par
# PM_CORE_DIR — même résolution que `pm-providers`. L'ignorer ferait lire au
# clone SA propre conf, donc un registre différent de celui qui gouverne.

def _load_arg_seen(core_dir):
    import pm_paths
    saved, seen = pm_paths.PMConfig.load, []

    class _Cfg:
        providers = {"servers": {}, "defaults": {}}

    def _spy(pm_dir=None):
        seen.append(pm_dir)
        return _Cfg()

    pm_paths.PMConfig.load = staticmethod(_spy)
    pm_forge._REGISTRY, pm_forge._REGISTRY_LOADED = None, False
    prev = os.environ.get("PM_CORE_DIR")
    if core_dir is None:
        os.environ.pop("PM_CORE_DIR", None)
    else:
        os.environ["PM_CORE_DIR"] = core_dir
    try:
        pm_forge._registry()
    finally:
        pm_paths.PMConfig.load = saved
        os.environ.pop("PM_CORE_DIR", None)
        if prev is not None:
            os.environ["PM_CORE_DIR"] = prev
    return seen


check("PM_CORE_DIR posé : transmis à PMConfig.load",
      _load_arg_seen("/un/core") == ["/un/core"])
check("PM_CORE_DIR absent : résolution par défaut (None)",
      _load_arg_seen(None) == [None])

with_registry(REG)

# ── 8. Les identifiants restent hors périmètre (RM2546) ────────────────────

with Env():
    os.environ["GOGS_TOKEN"] = "jeton-de-test"
    try:
        f = pm_forge.GogsForge("o/r", instance=REG.get("gogs-beta"))
        check("token : toujours lu dans l'environnement, pas dans le registre",
              f.token("worker") == "jeton-de-test")
    finally:
        os.environ.pop("GOGS_TOKEN", None)

pm_forge.set_registry(None)

if fails:
    print(f"\n✗ {len(fails)} échec(s)")
    raise SystemExit(1)
print("\nOK — pm_forge lit le registre (RM2766)")
