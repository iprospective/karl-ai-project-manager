"""pm_accounts — le registre des comptes PM de l'instance (RM3208, U1).

Les comptes du cockpit SONT ceux des utilisateurs du CLI (décision du 2026-09-16) : un seul registre,
`var/karl-users.json`, écrit par le cockpit (`/auth/users`) comme par `mmi-pm user`. Avant RM3208, toute
la logique vivait dans le serveur du cockpit : sans cockpit, personne ne pouvait créer un compte.

Ce que le module garantit, et qui ne dépend pas de l'appelant :
- jamais de mot de passe en clair : PBKDF2-HMAC-SHA256 salé, fichier en 0600 ;
- un compte peut exister SANS mot de passe (créé en CLI pour porter le rôle OS) : il n'ouvre alors
  aucune session cockpit, `password_ok` refuse tout ;
- écritures sérialisées ENTRE PROCESSUS (flock `pm_lock`, pas seulement un verrou de thread) : le démon et
  un `mmi-pm user` lancé en parallèle ne s'écrasent pas ;
- une écriture faite en root (`sudo mmi-pm user add`) rend le fichier à son propriétaire : le démon ne
  tourne pas en root et perdrait sinon l'accès à ses propres comptes.

Les verrous ne sont PAS réentrants (un flock par descripteur) : les fonctions publiques prennent le leur,
l'appelant ne doit donc pas les appeler sous `locked()` du même fichier.

Le superadmin (`KARL_WEB_USER`/`KARL_WEB_PASS` du .env) reste hors registre : amorçage garanti, insupprimable.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from contextlib import contextmanager
from pathlib import Path

from pm_lock import lock_for, resource_lock

PBKDF2_ITERATIONS = 310_000          # recommandation OWASP pour PBKDF2-HMAC-SHA256
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")
MIN_PASSWORD = 8
USERS_NAME = "karl-users.json"
DEVICES_NAME = "karl-devices.json"


class AccountError(Exception):
    """Refus métier, porteur du code HTTP que le cockpit renvoie tel quel."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def auth_dir(repo_root: Path) -> Path:
    """Dossier du registre : `KARL_AGENT_AUTH_DIR`, sinon `<racine du dépôt PM>/var` (comme le cockpit)."""
    return Path(os.environ.get("KARL_AGENT_AUTH_DIR") or (Path(repo_root) / "var"))


def load(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def target_owner(path: Path):
    """(uid, gid) à rendre au fichier après écriture : celui du fichier existant, sinon celui du dossier."""
    p = Path(path)
    ref = p if p.exists() else p.parent
    st = ref.stat()
    return st.st_uid, st.st_gid


def save(path: Path, data: dict) -> None:
    """Écriture atomique (temp du même dossier + rename) en 0600, propriétaire préservé si root."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    owner = target_owner(p)
    tmp = p.parent / f".{p.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}"
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.chmod(tmp, 0o600)
        if os.geteuid() == 0:
            os.chown(tmp, *owner)
        os.replace(tmp, p)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def locked(path: Path):
    """Verrou exclusif inter-processus sur un fichier du registre (non réentrant)."""
    with resource_lock(lock_for(path)):
        yield


def pbkdf2(password: str, salt_hex=None, iterations: int = PBKDF2_ITERATIONS) -> dict:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {"salt": salt.hex(), "iterations": iterations, "hash": dk.hex()}


def password_ok(password: str, rec: dict) -> bool:
    try:
        ref = pbkdf2(password, rec["salt"], int(rec["iterations"]))
        return hmac.compare_digest(ref["hash"], rec["hash"])
    except (KeyError, TypeError, ValueError):
        return False          # compte sans mot de passe, ou enregistrement abîmé : aucune session


def normalize_user(user) -> str:
    name = str(user or "").strip().lower()
    if not USERNAME_RE.match(name):
        raise AccountError(400, "user : 2-32 car., [a-z0-9._-], commence par [a-z0-9]")
    return name


def _check_password(password) -> None:
    if password is not None and len(str(password)) < MIN_PASSWORD:
        raise AccountError(400, f"pass : {MIN_PASSWORD} caractères minimum")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def revoke_devices(devices_path: Path, device_ids=None, user=None) -> int:
    with locked(devices_path):
        devices = load(devices_path)
        doomed = [d for d, r in devices.items()
                  if (device_ids and d in device_ids) or (user and r.get("user") == user)]
        for d in doomed:
            devices.pop(d, None)
        if doomed:
            save(devices_path, devices)
    return len(doomed)


def list_users(users_path: Path, devices_path: Path, superadmin=None) -> dict:
    users, devices = load(users_path), load(devices_path)
    per_user: dict = {}
    for rec in devices.values():
        per_user[rec.get("user")] = per_user.get(rec.get("user"), 0) + 1
    out = []
    for name, rec in sorted(users.items()):
        row = {"user": name, "disabled": bool(rec.get("disabled")), "created": rec.get("created"),
               "devices": per_user.get(name, 0), "password_set": "hash" in rec}
        if rec.get("os_role"):
            row["os_role"] = rec["os_role"]
        out.append(row)
    return {"users": out, "superadmin": superadmin}


def create_user(users_path: Path, user, password=None, superadmin=None, extra=None) -> dict:
    name = normalize_user(user)
    if superadmin is not None and name == str(superadmin).lower():
        raise AccountError(400, "ce nom est réservé au superadmin (.env)")
    _check_password(password)
    with locked(users_path):
        users = load(users_path)
        if name in users:
            raise AccountError(409, f"compte existant : {name}")
        rec = {**(extra or {}), "created": _now()}
        if password is not None:
            rec.update(pbkdf2(str(password)))
        users[name] = rec
        save(users_path, users)
    return {"user": name, "created": True}


def update_user(users_path: Path, devices_path: Path, user, password=None, disabled=None, extra=None) -> dict:
    name = str(user or "").strip().lower()
    _check_password(password)
    changed: dict = {}
    with locked(users_path):
        users = load(users_path)
        rec = users.get(name)
        if not rec:
            raise AccountError(404, f"compte inconnu : {name}")
        if password:
            rec.update(pbkdf2(str(password)))
            changed["pass"] = True
        if disabled is not None:
            rec["disabled"] = bool(disabled)
            changed["disabled"] = rec["disabled"]
        if extra:
            rec.update(extra)
            changed.update({k: True for k in extra})
        if not changed:
            raise AccountError(400, "rien à changer (pass et/ou disabled attendus)")
        users[name] = rec
        save(users_path, users)
    # mot de passe changé ou compte désactivé ⇒ les appareils existants sont révoqués
    if changed.get("disabled") or changed.get("pass"):
        changed["devices_revoked"] = revoke_devices(devices_path, user=name)
    return {"user": name, **changed}


def delete_user(users_path: Path, devices_path: Path, user) -> dict:
    name = str(user or "").strip().lower()
    with locked(users_path):
        users = load(users_path)
        if name not in users:
            raise AccountError(404, f"compte inconnu : {name}")
        users.pop(name)
        save(users_path, users)
    return {"user": name, "deleted": True, "devices_revoked": revoke_devices(devices_path, user=name)}
