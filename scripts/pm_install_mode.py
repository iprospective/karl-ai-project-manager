"""pm_install_mode — le mode d'installation de karl, déclaré et contrôlé (RM3070, lot L0).

Jusqu'ici le mode était DE FAIT : rien ne disait si karl servait un développeur seul
(`mono`) ou une équipe (`multi`), et chaque composant supposait l'un ou l'autre. Ce
module en fait une déclaration, lue au seul endroit où elle doit l'être :

    install:
      mode: mono        # mono | multi   (défaut : mono)

Ordre : `KARL_INSTALL_MODE` (posé par l'unité de service) > `install.mode` de la conf
fusionnée > `mono`. Même patron que les limites mémoire de karl-agent.

On ne DÉDUIT jamais le mode de l'environnement : c'est précisément parce qu'il n'était
écrit nulle part qu'il était implicite. On le CONTRÔLE : quatre signaux observables
(compte de service, règle sudoers, code root, plusieurs comptes) sont comparés au mode
déclaré, et chaque écart devient un avertissement — journalisé, exposé par /health,
jamais bloquant. Un signal qu'on ne peut pas lire vaut `None` et n'accuse personne.
"""
from __future__ import annotations

import json
import os
import pwd
from pathlib import Path

MODES = ("mono", "multi")
DEFAUT = "mono"
ENV = "KARL_INSTALL_MODE"
# Un compte de service se reconnaît à son nom ou à l'absence de shell de connexion.
COMPTES_SERVICE = "karl karl-agent".split()   # des noms de COMPTE, pas des stores
SHELLS_MUETS = ("/usr/sbin/nologin", "/sbin/nologin", "/bin/false", "/usr/bin/false")
SUDOERS = ("/etc/sudoers.d/karl", "/etc/sudoers.d/karl-agent")


def resoudre(conf: dict | None = None, env: dict | None = None) -> tuple[str, str, list[str]]:
    """Rend (mode, source, avertissements). Une valeur inconnue retombe sur le défaut,
    en le disant : une faute de frappe ne doit pas passer pour une décision."""
    env = os.environ if env is None else env
    avert = []
    brut, source = env.get(ENV), "env " + ENV
    if brut is None:
        brut = ((conf or {}).get("install") or {}).get("mode")
        source = "conf install.mode"
    if brut is None:
        return DEFAUT, "défaut", avert
    v = str(brut).strip().lower()
    if v not in MODES:
        avert.append(f"mode « {brut} » inconnu ({source}) — attendu mono ou multi ; "
                     f"{DEFAUT} retenu")
        return DEFAUT, "défaut", avert
    return v, source, avert


def _comptes(users_file: Path | None) -> int | None:
    if users_file is None:
        return None
    try:
        data = json.loads(Path(users_file).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 0
    except (OSError, ValueError):
        return None
    return len(data) if isinstance(data, dict) else None


def signaux(code_root: Path | None = None, users_file: Path | None = None,
            uid: int | None = None) -> dict:
    """Les quatre signaux observables. `None` = illisible (on ne conclut rien)."""
    uid = os.getuid() if uid is None else uid
    try:
        pw = pwd.getpwuid(uid)
        service = pw.pw_name in COMPTES_SERVICE or pw.pw_shell in SHELLS_MUETS
        compte = pw.pw_name
    except KeyError:
        service, compte = None, str(uid)
    sudoers = None
    try:
        sudoers = any(os.path.exists(p) for p in SUDOERS) or None
        # /etc/sudoers.d est souvent illisible pour un compte non root : l'absence
        # constatée n'est une preuve que si le répertoire se laisse lire.
        if sudoers is None and os.access("/etc/sudoers.d", os.R_OK | os.X_OK):
            sudoers = False
    except OSError:
        pass
    code = None
    if code_root is not None:
        try:
            code = Path(code_root).stat().st_uid == 0
        except OSError:
            pass
    return {"compte": compte, "compte_service": service, "sudoers": sudoers,
            "code_root": code, "comptes": _comptes(users_file)}


def ecarts(mode: str, sig: dict) -> list[str]:
    """Ce que les signaux contredisent dans le mode déclaré."""
    out = []
    if mode == "mono":
        if sig.get("compte_service"):
            out.append(f"mono déclaré, mais karl tourne sous un compte de service "
                       f"({sig.get('compte')})")
        if sig.get("sudoers"):
            out.append("mono déclaré, mais une règle sudoers karl est posée")
        if sig.get("code_root"):
            out.append("mono déclaré, mais le code appartient à root : la mise à jour "
                       "exigera sudo (lot L1)")
        if (sig.get("comptes") or 0) > 1:
            out.append(f"mono déclaré, mais {sig['comptes']} comptes cockpit existent")
    else:
        if sig.get("compte_service") is False:
            out.append(f"multi déclaré, mais karl tourne sous un compte personnel "
                       f"({sig.get('compte')}) : chaque utilisateur agirait avec ses droits")
        if sig.get("comptes") is not None and sig["comptes"] <= 1:
            out.append("multi déclaré, mais un seul compte cockpit existe")
    return out


def etat(conf: dict | None = None, code_root: Path | None = None,
         users_file: Path | None = None, env: dict | None = None) -> dict:
    """Le bloc exposé par /health : mode, sa source, les signaux et les écarts."""
    mode, source, avert = resoudre(conf, env)
    sig = signaux(code_root, users_file)
    return {"mode": mode, "source": source, "signals": sig,
            "warnings": avert + ecarts(mode, sig)}
