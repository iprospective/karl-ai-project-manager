"""pm_actor — QUI agit, quand karl agit pour quelqu'un (RM3070, lot L3).

Le démon fait tout sous SON compte. Tant qu'il n'y a qu'un développeur, cela ne se voit pas ;
dès qu'il y en a deux, les commits PM portent tous le même auteur et les journaux disent « le
service » là où ils devraient dire un nom. Ce module répond à une seule question — **qui est
l'acteur ?** — et la rend transportable jusqu'aux sous-processus, par l'environnement.

Trois sources, dans l'ordre, et **aucune invention** :

  1. la conf, table `identities:` — `<login>: {name, email}`, la vérité déclarée de l'instance ;
  2. le `~/.gitconfig` du développeur (`user.name` / `user.email`) quand il est lisible — c'est
     déjà l'identité qu'il utilise pour ses propres commits ;
  3. son nom réel (`gecos`) à défaut, **sans e-mail**.

Sans e-mail, on ne pose PAS d'auteur git : une adresse fabriquée signerait un commit au nom de
quelqu'un à une adresse qui n'est pas la sienne. Le nom voyage quand même (`PM_ACTOR_*`), donc
les journaux savent qui a agi, et git garde l'identité de la machine — ce qui est la vérité.

Git distingue AUTEUR et COMMITTER : l'auteur devient l'humain, le committer reste le compte de
service. « Écrit par Alice, enregistré par karl » est exactement ce qui s'est passé.
"""
from __future__ import annotations

import os
import pwd
import subprocess
from pathlib import Path

ENV_USER, ENV_NAME, ENV_EMAIL = "PM_ACTOR_USER", "PM_ACTOR_NAME", "PM_ACTOR_EMAIL"


def _conf_identity(login: str, conf: dict | None) -> dict:
    table = ((conf or {}).get("identities") or {})
    e = table.get(login) or {}
    return {"name": str(e.get("name") or "").strip(), "email": str(e.get("email") or "").strip()}


def _gitconfig_identity(home: Path) -> dict:
    """`user.name` / `user.email` du ~/.gitconfig, s'il est lisible. Un fichier illisible (droits
    d'un autre compte) ne lève pas : on n'en sait simplement rien."""
    f = Path(home) / ".gitconfig"
    out = {"name": "", "email": ""}
    if not f.is_file() or not os.access(f, os.R_OK):
        return out
    for cle, champ in (("user.name", "name"), ("user.email", "email")):
        try:
            r = subprocess.run(["git", "config", "--file", str(f), "--get", cle],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                out[champ] = r.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return out


def resolve(login: str, conf: dict | None = None) -> dict:
    """{user, name, email, source} — `email` peut être vide : c'est un résultat, pas un échec."""
    login = (login or "").strip()
    if not login:
        return {"user": "", "name": "", "email": "", "source": "inconnu"}
    ident = _conf_identity(login, conf)
    if ident["name"] and ident["email"]:
        return {"user": login, **ident, "source": "conf identities"}
    try:
        pw = pwd.getpwnam(login)
    except KeyError:
        return {"user": login, **ident, "source": "conf identities (compte système inconnu)"}
    git = _gitconfig_identity(Path(pw.pw_dir))
    nom = ident["name"] or git["name"] or (pw.pw_gecos or "").split(",")[0].strip() or login
    mail = ident["email"] or git["email"]
    source = "conf identities" if (ident["name"] or ident["email"]) else (
        "~/.gitconfig" if (git["name"] or git["email"]) else "compte système")
    return {"user": login, "name": nom, "email": mail, "source": source}


def env_for(acteur: dict, base: dict | None = None) -> dict:
    """L'environnement d'un sous-processus agissant POUR cet acteur.

    `PM_ACTOR_*` voyage toujours (les journaux ont un nom) ; `GIT_AUTHOR_*` seulement si l'adresse
    est connue — voir l'en-tête : pas d'adresse inventée."""
    env = dict(os.environ if base is None else base)
    for var in (ENV_USER, ENV_NAME, ENV_EMAIL, "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL"):
        env.pop(var, None)                      # jamais l'acteur d'une action précédente
    if not acteur or not acteur.get("user"):
        return env
    env[ENV_USER] = acteur["user"]
    if acteur.get("name"):
        env[ENV_NAME] = acteur["name"]
    if acteur.get("email"):
        env[ENV_EMAIL] = acteur["email"]
        env["GIT_AUTHOR_NAME"] = acteur.get("name") or acteur["user"]
        env["GIT_AUTHOR_EMAIL"] = acteur["email"]
    return env


def courant(env: dict | None = None) -> dict:
    """L'acteur porté par l'environnement (côté script appelé). Vide si personne n'a été posé."""
    e = os.environ if env is None else env
    return {"user": e.get(ENV_USER, ""), "name": e.get(ENV_NAME, ""), "email": e.get(ENV_EMAIL, "")}


def git_author_env(env: dict | None = None, base: dict | None = None) -> dict:
    """L'environnement à donner à `git commit` : auteur = l'humain quand on le connaît.

    Le COMMITTER n'est pas touché — il reste le compte qui exécute, et c'est voulu : le commit
    dit alors « écrit par X, enregistré par le service », ce qui est ce qui s'est passé."""
    a = courant(env)
    out = dict(os.environ if base is None else base)
    if a["email"]:
        out["GIT_AUTHOR_NAME"] = a["name"] or a["user"]
        out["GIT_AUTHOR_EMAIL"] = a["email"]
    return out
