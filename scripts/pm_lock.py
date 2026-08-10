"""pm_lock — verrous PAR RESSOURCE (flock) + écriture atomique (RM2551 / T7).

Remplace le single-writer GLOBAL (RM1669) par une sérialisation par ressource des
read-modify-write de fichiers partagés (multi-user, RM2438 / RM2502). L'arbitre
sémantique inter-process/inter-machine reste le verrou optimiste `updated` de
Redmine ; ici on protège la fenêtre RMW LOCALE.

Primitives :
    from pm_lock import resource_lock, atomic_write, lock_for, LockTimeout

    with resource_lock(lock_for(state_path)):     # flock exclusif, attente bornée
        data = read(state_path)
        atomic_write(state_path, transform(data))  # temp same-dir + os.replace

Contention = écriture DIFFÉRÉE, jamais rejetée : le writer ATTEND (flock non-bloquant
en boucle + sleep court avec jitter) jusqu'à `timeout` ; au-delà seulement, échec
EXPLICITE (`LockTimeout`) — un lock court ne devrait jamais tenir aussi longtemps,
donc le dépassement EST le signal d'une anomalie.

Robustesse crash — PAS de verrou fantôme par construction : `flock(2)` est un verrou
advisory NOYAU attaché à l'*open file description*. À la mort du process (crash, kill,
OOM), le noyau ferme le fd et libère le lock AUTOMATIQUEMENT. Le fichier `.lock` peut
subsister : il est INERTE (l'état de verrou = le flock, pas l'existence du fichier).
⚠ Fiable sur FS LOCAL (ici ZFS), PAS sur NFS.
"""
import errno
import fcntl
import os
import random
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Union

_PathLike = Union[str, "os.PathLike[str]"]


class LockTimeout(TimeoutError):
    """La ressource est restée verrouillée au-delà du `timeout` (anomalie probable)."""


def lock_for(data_path: _PathLike) -> Path:
    """Chemin de `.lock` sidecar conventionnel pour un fichier de données.

    `…/tasks/RM42.md` → `…/tasks/.RM42.md.lock` (caché, même répertoire → mêmes
    droits de groupe que la donnée). Le `.lock` est un fichier de verrouillage
    dédié : on ne verrouille jamais la donnée elle-même (elle est remplacée
    atomiquement, son inode change)."""
    p = Path(data_path)
    return p.parent / f".{p.name}.lock"


@contextmanager
def resource_lock(lock_file: _PathLike, *, timeout: float = 10.0, poll: float = 0.05):
    """Verrou exclusif sur `lock_file` (flock), attente bornée à `timeout` secondes.

    Bloque tant que la ressource est prise (re-tente toutes ~`poll` s + jitter).
    Lève `LockTimeout` au-delà de `timeout`. Libéré à la sortie du bloc ET, quoi
    qu'il arrive, à la mort du process (flock noyau)."""
    lp = Path(lock_file)
    lp.parent.mkdir(parents=True, exist_ok=True)
    # 0o664 : group-writable → tout membre du groupe `pm` peut verrouiller (dirs 3770).
    fd = os.open(lp, os.O_CREAT | os.O_RDWR, 0o664)
    deadline = time.monotonic() + max(0.0, timeout)
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                    raise
                if time.monotonic() >= deadline:
                    raise LockTimeout(
                        f"ressource {lp.name} occupée > {timeout:g}s — réessaie "
                        f"(un lock court ne devrait jamais tenir aussi longtemps)"
                    ) from None
                time.sleep(poll + random.uniform(0.0, poll))  # jitter anti-thundering-herd
        yield lp
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def atomic_write(
    path: _PathLike, data: Union[str, bytes], *, encoding: str = "utf-8"
) -> Path:
    """Écriture ATOMIQUE : écrit dans un temp du MÊME répertoire puis `os.replace`
    (rename atomique POSIX). Un lecteur concurrent ne voit jamais un fichier
    à moitié écrit — il voit l'ancien OU le nouveau, jamais un entre-deux.

    Préserve les droits du fichier cible existant (fichiers partagés group-writable).
    À combiner avec `resource_lock` pour ceinturer la fenêtre RMW."""
    p = Path(path)
    tmp = p.parent / f".{p.name}.tmp.{os.getpid()}.{random.randint(0, 1 << 30)}"
    try:
        if isinstance(data, bytes):
            tmp.write_bytes(data)
        else:
            tmp.write_text(data, encoding=encoding)
        try:  # préserver le mode de la cible (droits de groupe des fichiers partagés)
            os.chmod(tmp, os.stat(p).st_mode & 0o7777)
        except FileNotFoundError:
            pass  # nouveau fichier → mode par défaut (umask)
        os.replace(tmp, p)  # atomique si tmp et p sont sur le même FS (même dir → oui)
        return p
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass  # déjà renommé (cas nominal) ou jamais créé
