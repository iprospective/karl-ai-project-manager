#!/usr/bin/env python3
"""Tests RM2888 — GET /ticket-transitions/<rm> (les statuts posables sur un ticket).

Ce qu'on protège ici, c'est le contrat CÔTÉ COCKPIT, sans réseau ni Redmine :
le script `pm-task-status-update --list-next --json` est simulé, parce que ce
qu'on éprouve n'est pas la table NORMS (elle a ses propres tests) mais ce que le
cockpit en fait — id validé avant tout lancement de processus, JSON relayé tel
quel, erreurs traduites en codes utiles, et cache court pour ne pas relancer un
interpréteur à chaque ouverture de menu.

Lancer : python3 scripts/test_karl_agent_transitions.py
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
import types

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(cond, label):
    if cond:
        print(f"  ✓ {label}")
    else:
        fails.append(label)
        print(f"  ✗ {label}", file=sys.stderr)


class FakeRun:
    """Remplace subprocess.run : compte les lancements, rejoue une sortie figée."""

    def __init__(self, stdout="", stderr="", rc=0):
        self.stdout, self.stderr, self.rc, self.calls = stdout, stderr, rc, []

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        return types.SimpleNamespace(returncode=self.rc, stdout=self.stdout, stderr=self.stderr)


def with_run(fake):
    ka.subprocess = types.SimpleNamespace(run=fake, TimeoutExpired=subprocess.TimeoutExpired)
    ka._transitions_cache.clear()


PAYLOAD = {"rm_id": 42, "status": "en_cours", "redmine_checked": True,
           "transitions": [{"status": "a_tester_dev", "condition": "dev terminé",
                            "redmine_ok": True, "needs_close_reason": False,
                            "needs_note": False}],
           "close_reasons": ["resolu"]}

# ── Un id est validé AVANT de lancer quoi que ce soit ───────────────────────
fake = FakeRun(stdout=json.dumps(PAYLOAD))
with_run(fake)
for bad in ("../etc/passwd", "42; rm -rf /", "", "abc"):
    try:
        ka.op_ticket_transitions(bad)
        check(False, f"id refusé : {bad!r}")
    except ka.ApiError as e:
        check(e.code == 400, f"id refusé en 400 (pas de processus lancé) : {bad!r}")
check(not fake.calls, "aucun sous-processus lancé pour un id invalide")

# ── Cas nominal : le JSON du script est relayé tel quel ─────────────────────
with_run(fake)
d = ka.op_ticket_transitions("42")
check(d["status"] == "en_cours" and d["transitions"][0]["status"] == "a_tester_dev",
      "la sortie du script est relayée sans réinterprétation")
check(any("--list-next" in a and "--json" in a for a in [" ".join(c) for c in fake.calls]),
      "…et vient bien de `--list-next --json` : la règle n'est pas recalculée ici")

# ── Cache court : ouvrir deux fois un menu ne relance pas l'interpréteur ────
before = len(fake.calls)
again = ka.op_ticket_transitions("42")
check(len(fake.calls) == before and again.get("cached") is True,
      "un second appel immédiat est servi par le cache, et le dit")
forced = ka.op_ticket_transitions("42", force=True)
check(len(fake.calls) == before + 1 and not forced.get("cached"),
      "`force=1` relance vraiment : après un changement de statut, le cache est faux")

# ── Erreurs : traduites en codes exploitables, pas en 500 muet ──────────────
with_run(FakeRun(stderr="ERREUR : fichier RM999999_*.md introuvable", rc=1))
try:
    ka.op_ticket_transitions("999999")
    check(False, "ticket inconnu → 404")
except ka.ApiError as e:
    check(e.code == 404, "ticket inconnu → 404, avec le message du script")

with_run(FakeRun(stdout="pas du json", rc=0))
try:
    ka.op_ticket_transitions("42")
    check(False, "sortie illisible → 500")
except ka.ApiError as e:
    check(e.code == 500, "sortie illisible → 500 explicite plutôt qu'une exception nue")

# ── La route existe et est branchée ────────────────────────────────────────
src = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check('path.startswith("/ticket-transitions/")' in src, "la route GET est déclarée")
check("GET  /ticket-transitions/<rm>" in src, "…et documentée dans l'en-tête des routes")

print()
if fails:
    print(f"✗ {len(fails)} échec(s)", file=sys.stderr)
    sys.exit(1)
print("✓ tests /ticket-transitions OK")
