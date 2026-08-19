#!/usr/bin/env python3
"""Tests de la généralisation du verrou de pm-wiki-sync sur pm_lock (T7/RM2551).

Lancer : python3 scripts/test_pm_wiki_sync_lock.py
Couvre : ProjectLock acquiert/libère + contention → LockBusy (mappé depuis
LockTimeout), save_state écrit un state.json valide sans temp résiduel (atomic_write).
La crash-safety flock est déjà couverte par test_pm_lock (ProjectLock délègue).
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def _load_wiki_sync():
    spec = importlib.util.spec_from_file_location("pm_wiki_sync", SCRIPTS / "pm-wiki-sync.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    m = _load_wiki_sync()

    with tempfile.TemporaryDirectory() as d:
        sd = Path(d) / ".wiki-sync"

        # 1. acquire / release
        with m.ProjectLock(sd):
            assert sd.exists()
        with m.ProjectLock(sd, timeout=0.5):
            pass
        print("✓ ProjectLock : acquire / release (flock)")

        # 2. contention (2 verrous même process, OFD distincts) → LockBusy
        with m.ProjectLock(sd):
            try:
                with m.ProjectLock(sd, timeout=0.2):
                    raise AssertionError("aurait dû lever LockBusy")
            except m.LockBusy:
                pass
        print("✓ contention → LockBusy (LockTimeout mappé, skip préservé)")

        # 3. save_state / load_state : contenu valide, écriture atomique
        state = {"schema": 1, "targets": {"a": {"h": "x"}}}
        m.save_state(sd, state)
        assert m.load_state(sd) == state, "roundtrip state.json"
        assert (sd / "state.json").is_file()
        assert not list(sd.glob(".state.json.tmp*")), "pas de temp résiduel"
        m.save_state(sd, {"schema": 1, "targets": {}})  # ré-écriture
        assert m.load_state(sd)["targets"] == {}
        print("✓ save_state/load_state : roundtrip, atomique, pas de temp résiduel")

    print("\nOK — tests pm-wiki-sync (verrou pm_lock) passent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
