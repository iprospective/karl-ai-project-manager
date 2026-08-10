#!/usr/bin/env python3
"""Tests de pm_lock — verrous par ressource + écriture atomique (T7/RM2551).

Lancer : python3 scripts/test_pm_lock.py
Couvre : lock_for, acquire/release + ré-acquisition, contention → LockTimeout
(attente bornée), atomic_write (contenu/mode/bytes/pas de temp résiduel), et
crash-safety RÉELLE (SIGKILL d'un process tenant le verrou → le noyau libère).
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from pm_lock import resource_lock, atomic_write, lock_for, LockTimeout  # noqa: E402


def test_lock_for():
    assert lock_for("/a/b/RM42.md") == Path("/a/b/.RM42.md.lock")
    print("✓ lock_for : sidecar caché, même répertoire")


def test_acquire_release(tmp):
    lp = tmp / "r.lock"
    with resource_lock(lp):
        assert lp.exists()
    with resource_lock(lp, timeout=0.5):  # ré-acquisition après libération
        pass
    print("✓ acquire/release + ré-acquisition après libération")


def test_contention(tmp):
    lp = tmp / "c.lock"
    with resource_lock(lp):
        t0 = time.monotonic()
        try:
            with resource_lock(lp, timeout=0.3):
                raise AssertionError("aurait dû lever LockTimeout")
        except LockTimeout:
            pass
        assert time.monotonic() - t0 >= 0.3, "n'a pas attendu le timeout"
    print("✓ contention (même process, 2 OFD) → LockTimeout après attente bornée")


def test_atomic_write(tmp):
    p = tmp / "data.txt"
    atomic_write(p, "v1")
    assert p.read_text() == "v1"
    os.chmod(p, 0o664)
    atomic_write(p, "v2")
    assert p.read_text() == "v2", "contenu remplacé"
    assert (p.stat().st_mode & 0o777) == 0o664, "mode cible préservé"
    assert not list(tmp.glob(".data.txt.tmp*")), "pas de temp résiduel"
    pb = tmp / "b.bin"
    atomic_write(pb, b"\x00\x01\x02")
    assert pb.read_bytes() == b"\x00\x01\x02", "bytes"
    print("✓ atomic_write : contenu, mode préservé, bytes, pas de temp résiduel")


def test_crash_safety(tmp):
    lp = tmp / "crash.lock"
    ready = tmp / "ready"
    child_py = tmp / "child.py"
    child_py.write_text(
        "import time, sys, pathlib\n"
        f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
        "from pm_lock import resource_lock\n"
        f"ctx = resource_lock({str(lp)!r}, timeout=5)\n"
        "ctx.__enter__()\n"
        f"pathlib.Path({str(ready)!r}).write_text('1')\n"
        "time.sleep(60)\n"
    )
    child = subprocess.Popen([sys.executable, str(child_py)])
    try:
        for _ in range(100):
            if ready.exists():
                break
            time.sleep(0.05)
        assert ready.exists(), "l'enfant n'a pas acquis le verrou"
        # tant que l'enfant tient : le parent ne peut pas acquérir
        try:
            with resource_lock(lp, timeout=0.3):
                raise AssertionError("aurait dû timeout (enfant tient le verrou)")
        except LockTimeout:
            pass
        # CRASH simulé : SIGKILL (aucune libération applicative possible)
        child.kill()
        child.wait()
        # le noyau a libéré le flock → le parent acquiert immédiatement
        t0 = time.monotonic()
        with resource_lock(lp, timeout=2):
            pass
        assert time.monotonic() - t0 < 1.0, "acquisition lente → verrou fantôme ?"
        print("✓ crash-safety : SIGKILL du détenteur → verrou libéré par le noyau (pas de fantôme)")
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def main():
    test_lock_for()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_acquire_release(tmp)
        test_contention(tmp)
        test_atomic_write(tmp)
        test_crash_safety(tmp)
    print("\nOK — tests pm_lock passent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
