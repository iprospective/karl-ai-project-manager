#!/usr/bin/env python3
"""Tests RM2810 — garde « session vivante » de pm_proclive.

Hermétique : aucun process réel, aucun réseau. On pointe `pm_proclive.PROC` sur
un faux /proc peuplé de fichiers `cmdline`, ce qui permet de rejouer exactement
les trois situations qui mettaient l'ancienne garde en défaut.

Lancer : python3 scripts/test_pm_proclive.py
"""
import importlib.util
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_proclive", HERE / "pm_proclive.py")
pl = importlib.util.module_from_spec(spec)
sys.modules["pm_proclive"] = pl
spec.loader.exec_module(pl)

SID = "62e4136f-dda6-4ced-b9aa-63df5439158d"
OTHER = "11111111-2222-3333-4444-555555555555"

FAILURES = []


def fake_proc(procs: dict) -> pathlib.Path:
    """procs = {pid: [argv...]} -> racine d'un /proc factice."""
    root = pathlib.Path(tempfile.mkdtemp())
    for pid, argv in procs.items():
        d = root / str(pid)
        d.mkdir()
        (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    # Bruit non numérique, comme dans un vrai /proc.
    (root / "meminfo").write_text("")
    (root / "self").mkdir()
    return root


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: attendu={want} obtenu={got}")
    if not ok:
        FAILURES.append(label)


def run(label, procs, sid=SID, engine="claude"):
    pl.PROC = fake_proc(procs)
    return pl.live_session_pids(sid, engine)


print("RM2810 — détection d'une session vivante\n")

# --- faux négatif : le cas dangereux ---------------------------------------
print("faux négatif (l'ancienne garde exigeait --resume) :")
check("session neuve --session-id détectée",
      run("", {101: ["claude", "--session-id", SID]}), [101])
check("session sans aucun drapeau détectée",
      run("", {102: ["claude", SID]}), [102])
check("session --resume toujours détectée",
      run("", {103: ["claude", "--resume", SID]}), [103])

# --- faux positif : le cas rencontré ---------------------------------------
print("\nfaux positif (l'ancienne garde matchait toute ligne pgrep) :")
check("commande shell citant le sid ET --resume ignorée",
      run("", {201: ["/bin/bash", "-c", f"echo claude --resume {SID}"]}), [])
check("le script de déplacement lui-même ignoré",
      run("", {202: ["python3", "karl-move-session.py", "--session", SID]}), [])
check("un grep sur le sid ignoré",
      run("", {203: ["grep", "-rn", SID, "/home"]}), [])

# --- exactitude générale ---------------------------------------------------
print("\nexactitude :")
check("un autre sid ne déclenche rien",
      run("", {301: ["claude", "--resume", OTHER]}), [])
check("plusieurs process du même sid, triés",
      run("", {402: ["claude", "--resume", SID], 401: ["claude", "--session-id", SID]}), [401, 402])
check("claude lancé via node reconnu",
      run("", {501: ["node", "/opt/claude/cli/claude", "--resume", SID]}), [501])
check("node exécutant AUTRE CHOSE ignoré",
      run("", {502: ["node", "/opt/tools/watcher.js", "--resume", SID]}), [])
check("moteur alternatif respecté (opencode)",
      run("", {601: ["opencode", "--session", SID]}, engine="opencode"), [601])
check("le moteur claude ne voit pas opencode",
      run("", {602: ["opencode", "--session", SID]}), [])
check("sid vide ne remonte rien",
      run("", {701: ["claude", "--resume", SID]}, sid=""), [])
check("aucun process : liste vide",
      run("", {}), [])

# --- session_is_live ---------------------------------------------------------
print("\nsession_is_live :")
pl.PROC = fake_proc({801: ["claude", "--session-id", SID]})
check("booléen vrai", pl.session_is_live(SID), True)
pl.PROC = fake_proc({802: ["/bin/bash", "-c", f"cat {SID}"]})
check("booléen faux", pl.session_is_live(SID), False)

print()
if FAILURES:
    print(f"✗ {len(FAILURES)} test(s) en échec : {', '.join(FAILURES)}")
    sys.exit(1)
print("✓ tous les tests passent")
