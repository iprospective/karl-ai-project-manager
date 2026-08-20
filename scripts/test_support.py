#!/usr/bin/env python3
"""Socle commun des tests hors ligne (RM2749) — un environnement PM JETABLE.

Le problème réglé ici : `PMConfig.load()` a besoin d'un `roots.projects_root`
résolu, qui vient de `$PROJECTS_PATH` — porté par le `.env` canonique, absent
d'un clone de dev. Sans lui, `load()` appelle `sys.exit()`. Utile pour un script
lancé à la main (le message explique clone-dev vs runtime canonique), fatal pour
un test : `sys.exit` lève un `SystemExit`, qui n'est PAS attrapé par un
`except Exception`. Deux conséquences, toutes deux constatées sur `dev` :

  - le test meurt en cours de route (`karl_agent_envstatus`, `pm_session_status_*`) ;
  - ou pire, l'appelant rattrape la sortie pour DÉGRADER vers la configuration
    livrée, en silence — le test tourne alors contre la mauvaise config et
    échoue en annonçant « instance inconnue » (`vault_agentd_multi`,
    `pm_secrets_keepass`), ce qui envoie chercher le défaut là où il n'est pas.

Avant ce module, un même test changeait donc de verdict selon que `PM_CORE_DIR`
était exporté dans le shell : cinq tests basculaient d'un shell à l'autre, et
« la suite passe » ne voulait rien dire tant qu'on ne précisait pas
l'environnement. La réponse n'est PAS d'exiger un `.env` — ce serait déplacer le
problème sur le poste, et faire lire au test la configuration de PRODUCTION.
C'est de donner au test son propre core minimal, dans un dossier temporaire :
rien à installer, même verdict partout, et aucun risque de toucher au runtime.

Usage :

    from test_support import hermetic_core, subprocess_env

    hermetic_core()                       # AVANT d'importer un module PM
    env = subprocess_env(PM_X="y")        # pour un subprocess.run(..., env=env)

Pour un test qui lance un daemon sur SA configuration (instances de vault
supplémentaires), voir `core_with()` / `core_env()` plus bas.
"""
import os
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

#: Variables qui, héritées du shell appelant, ramèneraient un script vers le
#: core RÉEL — c'est par elles que le verdict d'un test se mettait à dépendre
#: de l'environnement d'exécution.
INHERITED = ("PM_CORE_DIR", "PM_DEV_DIR", "PM_CONFIG", "PM_DIR", "PROJECTS_PATH",
             "PM_CONF_DIR", "PM_STATE_DIR", "PM_LOG_DIR", "PM_USER_ENV")

_CORE = None
_TMP = None      # référence gardée : sa destruction effacerait le core


def hermetic_core() -> Path:
    """Crée (une fois par processus) un core PM jetable et pointe dessus.

    Contenu minimal : un `.env` définissant `PROJECTS_PATH`, seule racine dont
    `PMConfig.load()` a besoin pour ne pas sortir en erreur. Aucun secret — un
    core de test n'a rien à résoudre. Le dossier vit jusqu'à la fin du
    processus : les tests n'ont pas à le nettoyer.

    `PROJECTS_PATH` est retiré de l'environnement en plus d'être écrit dans le
    `.env` : `_load_env_file` n'écrase jamais l'existant, donc une valeur déjà
    exportée primerait sur celle du core et le test lirait la vraie arborescence.
    """
    global _CORE, _TMP
    if _CORE is None:
        _TMP = tempfile.TemporaryDirectory(prefix="pm-core-test-")
        _CORE = Path(_TMP.name)
        (_CORE / "projects").mkdir()
        (_CORE / ".env").write_text(
            "# core JETABLE de test (RM2749) — aucun secret, aucune adresse réelle\n"
            f"PROJECTS_PATH={_CORE / 'projects'}\n",
            encoding="utf-8",
        )
    for k in INHERITED:
        os.environ.pop(k, None)
    os.environ["PM_CORE_DIR"] = str(_CORE)
    return _CORE


def subprocess_env(**extra) -> dict:
    """L'environnement à passer à un `subprocess.run` de script PM.

    Part de l'environnement courant purgé des variables héritées, force le core
    jetable, puis applique `extra`. Une valeur à `None` retire la variable —
    pratique pour prouver qu'un script se débrouille sans elle.
    """
    core = hermetic_core()
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env["PM_CORE_DIR"] = str(core)
    for k, v in extra.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = str(v)
    return env


def core_with(work, servers: dict, config_src=None) -> Path:
    """Core de test posé dans `work`, avec des instances AJOUTÉES aux providers.

    Variante de `hermetic_core()` pour les tests qui lancent un DAEMON sur leur
    propre configuration (vault-agentd, multi-instances) : ils ont besoin d'un
    vrai `pm.config.yml`, pas seulement d'un `PROJECTS_PATH`.

    Le `pm.env` posé ici est le fichier d'INSTANCE, non-secret (RM2438 T1) : y
    mettre un secret serait un contresens, il est group-readable par
    construction. L'ajout des instances passe par le YAML chargé, pas par une
    insertion de texte à une ancre (`    vw-ipro:`) : une ancre suit la mise en
    page du fichier livré et casse dès qu'on le retouche, sans dire pourquoi.
    """
    import yaml

    core = Path(work)
    core.mkdir(parents=True, exist_ok=True)
    src = Path(config_src) if config_src else (SCRIPTS.parent / "pm.config.yml")
    cfg = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    cfg.setdefault("providers", {}).setdefault("servers", {}).update(servers or {})
    (core / "pm.config.yml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    projects = core / "projects"
    projects.mkdir(exist_ok=True)
    (core / "pm.env").write_text(f"PROJECTS_PATH={projects}\n", encoding="utf-8")
    # Les scripts sont cherchés à côté de la config : on lie ceux du dépôt pour
    # que le core de test reste une simple surcouche du code réel.
    if not (core / "scripts").exists():
        (core / "scripts").symlink_to(SCRIPTS)
    return core


def core_env(core, **extra) -> dict:
    """Environnement d'un sous-processus visant le core rendu par `core_with()`."""
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env["PM_CORE_DIR"] = str(core)
    env.update({k: str(v) for k, v in extra.items()})
    return env
