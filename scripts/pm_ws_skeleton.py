"""pm_ws_skeleton — pont vers le verbe privilégié `pm-env-helper ws-init` (RM2909).

Le modèle de perms multi-user (RM2438 / T6 RM2502) verrouille la racine d'un workspace
en `2750 pm:pm` : group `r-x`, **pas d'écriture** (invariant anti-déstructuration,
volontaire). Conséquence directe, constatée trois fois sur la création de
`iprospective/communication` le 2026-08-31 : `pm-project-new` et `pm-env-init` — qui
écrivent sous l'identité de l'appelant — échouent en `Permission denied` sur `.mmi-pm/`,
`repos/`, `envs/` et les dossiers partagés du layout. Il fallait encadrer chaque
création de projet par deux `sudo` humains interactifs.

Ce module est le pont. Quand — et SEULEMENT quand — le workspace n'est pas inscriptible,
on passe par le helper NOPASSWD, qui crée le squelette puis applique le modèle. Aucun
`sudo` interactif, et aucune duplication du modèle : le helper le tient de `pm-perms`.

**Non bloquant par construction.** Sur une box sans le modèle multi-user, ou sur un
workspace historique `mathieu:mathieu` déjà inscriptible, ces fonctions ne font RIEN et
l'appelant se comporte exactement comme avant. Elles n'ont pas vocation à migrer un
workspace existant : `apply_perms` ne touche qu'un workspace DÉJÀ au modèle (owner `pm`),
jamais un workspace legacy — une migration se décide, elle ne se subit pas au détour
d'un `pm-env-init`.
"""
import importlib.util
import os
import pwd
import shutil
import subprocess
from pathlib import Path

HELPER = "/usr/local/sbin/pm-env-helper"


def _model_dirs():
    """Dossiers du modèle, lus dans pm-perms — la seule définition qui fasse foi.
    Liste vide si indisponible : on ne devine pas un modèle, on s'abstient."""
    try:
        src = Path(__file__).resolve().parent / "pm-perms.py"
        spec = importlib.util.spec_from_file_location("pm_perms", src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return [r for r in mod.model_dirs() if r != "."]
    except Exception:
        return []


def missing_pieces(ws: Path) -> list:
    """Pièces de SQUELETTE absentes — celles dont la création à la racine est réservée
    au privilège par le mode 2750 (dossiers du modèle + whitelist du repo `-core`)."""
    return [rel for rel in [*_model_dirs(), ".gitignore"] if not (ws / rel).exists()]


def _helper_available() -> bool:
    return os.access(HELPER, os.X_OK) and shutil.which("sudo") is not None


def _pm_uid():
    try:
        return pwd.getpwnam("pm").pw_uid
    except KeyError:
        return None


def is_model_workspace(ws: Path) -> bool:
    """Le workspace est-il au modèle multi-user (racine possédée par `pm`) ?"""
    pm_uid = _pm_uid()
    try:
        return pm_uid is not None and ws.stat().st_uid == pm_uid
    except OSError:
        return False


def _run(verb: str, ws: Path) -> bool:
    """Appelle le helper en NOPASSWD (`sudo -n` : jamais de prompt, jamais de blocage
    dans un hook ou une session d'agent). Retourne True si la mutation a réussi."""
    cmd = ["sudo", "-n", HELPER, verb, str(ws)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"  ⚠ {verb} : {e}")
        return False
    for line in (r.stdout or "").splitlines():
        print(f"  {line}")
    if r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()
        print(f"  ⚠ {HELPER} {verb} a échoué"
              + (f" : {err[-1]}" if err else "")
              + f"\n    → à la main : sudo {HELPER} {verb} {ws}")
        return False
    return True


def ensure_skeleton(ws: Path, dry: bool = False) -> bool:
    """Garantit que le squelette de `ws` existe, en déléguant au helper si besoin.

    Retourne True si le helper a effectivement été invoqué. Trois cas d'abstention, tous
    silencieux — le nominal ne doit rien dire :
      · le squelette est complet (rien à créer) ;
      · la racine est inscriptible (workspace historique : l'appelant se débrouille,
        comme avant, sans privilège) ;
      · pas de helper sur la box (modèle multi-user non provisionné)."""
    if ws.exists():
        manque = missing_pieces(ws)
        if not manque or os.access(ws, os.W_OK):
            return False
        quoi = ", ".join(manque[:4]) + ("…" if len(manque) > 4 else "")
        motif = f"racine 2750 non inscriptible, manque : {quoi}"
    else:
        motif = "workspace absent sous une racine client verrouillée"
    if not _helper_available():
        return False
    if dry:
        print(f"  [dry] sudo {HELPER} ws-init {ws}  ({motif})")
        return False
    print(f"  {motif} → délégation à {HELPER} ws-init")
    return _run("ws-init", ws)


def apply_perms(ws: Path, dry: bool = False) -> bool:
    """Réapplique le modèle de perms après création (verbe symétrique de `ws-init`).

    Restreint aux workspaces DÉJÀ au modèle : sur un workspace legacy, c'est un no-op
    — pas une migration silencieuse vers `pm:pm`."""
    if not is_model_workspace(ws) or not _helper_available():
        return False
    if dry:
        print(f"  [dry] sudo {HELPER} ws-perms {ws}")
        return False
    return _run("ws-perms", ws)
