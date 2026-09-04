#!/usr/bin/env python3
"""Tests de `next_transitions` — les statuts posables depuis un statut donné (RM2888).

Lancer : python3 scripts/test_pm_task_status_transitions.py

Ce qui est éprouvé ici, c'est le CONTRAT de la sortie machine consommée par le
cockpit (`--list-next --json`), pas la table NORMS elle-même : la table est la
norme, la recopier dans un test ne prouverait que la copie. On vérifie donc la
forme (clés présentes, types), les invariants qui protègent l'UI (pas de doublon,
`ferme` marqué comme exigeant un motif, réouverture marquée comme exigeant une
note) et le MODE DÉGRADÉ — sans Redmine joignable, la liste doit rester complète
et se dire non vérifiée, sinon une panne d'API rendrait le geste inatteignable.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from test_support import hermetic_core, subprocess_env      # noqa: E402

hermetic_core()                                             # AVANT l'import du module PM

_spec = importlib.util.spec_from_file_location(
    "pm_task_status_update", str(_HERE / "pm-task-status-update.py"))
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def fake_task(tmp: Path, rm_id: int, status: str, history=None) -> Path:
    """Un MD de tâche minimal, suffisant pour `next_transitions`."""
    hist = "".join(f"\n- status: {h}\n  at: 2026-01-0{i + 1}T10:00"
                   for i, h in enumerate(history or []))
    p = tmp / f"RM{rm_id}_test.md"
    p.write_text(
        "---\n"
        f"redmine_id: {rm_id}\n"
        "title: 'Ticket de test'\n"
        f"status: {status}\n"
        f"status_history:{hist if hist else ' []'}\n"
        "updated: 2026-01-01T10:00\n"
        "---\n\n## Contexte\n", encoding="utf-8")
    return p


def transitions_for(tmp, rm_id, status, history=None):
    """`next_transitions` sur une tâche fabriquée, sans réseau."""
    path = fake_task(tmp, rm_id, status, history)
    mod.PMConfig.load = staticmethod(lambda: type("C", (), {"find_task": lambda self, i: path})())
    return mod.next_transitions(rm_id, check_redmine=False)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pm-transitions-"))
    ko = 0

    def check(cond, label):
        nonlocal ko
        if cond:
            print(f"  ✓ {label}")
        else:
            ko += 1
            print(f"  ✗ {label}", file=sys.stderr)

    # ── Forme du contrat ────────────────────────────────────────────────────
    d = transitions_for(tmp, 9001, "en_cours")
    check(d["status"] == "en_cours", "le statut courant est rendu tel quel")
    check(isinstance(d["transitions"], list) and d["transitions"],
          "un ticket en cours a des transitions")
    keys = {"status", "condition", "redmine_ok", "needs_close_reason", "needs_note"}
    check(all(keys <= set(t) for t in d["transitions"]),
          "chaque transition porte le contrat complet attendu par l'UI")
    check(all(t["redmine_ok"] is None for t in d["transitions"]),
          "sans vérification live, `redmine_ok` vaut None — jamais False")
    check(d["redmine_checked"] is False,
          "…et `redmine_checked` le dit : « refusé » et « pas vérifié » ne se confondent pas")
    check(json.dumps(d) and isinstance(json.dumps(d), str), "la structure est sérialisable telle quelle")

    # ── Invariants qui protègent l'UI ───────────────────────────────────────
    sts = [t["status"] for t in d["transitions"]]
    check(len(sts) == len(set(sts)), "aucun doublon : `en_pause`/`ferme` génériques ne doublent pas une règle")
    check(sts.count("ferme") == 1 and next(t for t in d["transitions"] if t["status"] == "ferme")["needs_close_reason"],
          "la fermeture est marquée comme exigeant un motif")
    check(all(not t["needs_close_reason"] for t in d["transitions"] if t["status"] != "ferme"),
          "…et elle seule")

    # ── Statuts particuliers ────────────────────────────────────────────────
    closed = transitions_for(tmp, 9002, "ferme")
    check([t["status"] for t in closed["transitions"]] == ["a_faire"],
          "un ticket fermé ne propose que la réouverture")
    check(closed["transitions"][0]["needs_note"],
          "…qui exige sa note : le motif de réouverture est dans les NORMS")

    paused = transitions_for(tmp, 9003, "en_pause", history=["a_faire", "en_cours"])
    check("en_cours" in [t["status"] for t in paused["transitions"]],
          "une pause se reprend à l'état précédent, lu dans l'historique")
    check("en_pause" not in [t["status"] for t in paused["transitions"]],
          "…et ne se re-met pas en pause")

    check(all(t["status"] != "en_pause" for t in closed["transitions"]),
          "un ticket fermé ne se met pas en pause non plus")

    # ── La sortie CLI --json est bien celle-là ──────────────────────────────
    # (contrat de bout en bout : c'est cette commande que le cockpit exécute)
    proc = subprocess.run(
        [sys.executable, str(_HERE / "pm-task-status-update.py"), "999999", "--list-next", "--json"],
        capture_output=True, text=True, env=subprocess_env(), timeout=60)
    check(proc.returncode != 0 and "introuvable" in (proc.stderr + proc.stdout),
          "un ticket inconnu échoue clairement, sans JSON tronqué à parser")

    proc = subprocess.run(
        [sys.executable, str(_HERE / "pm-task-status-update.py"), "1", "--json"],
        capture_output=True, text=True, env=subprocess_env(), timeout=60)
    check(proc.returncode != 0 and "--list-next" in (proc.stderr + proc.stdout),
          "`--json` seul est refusé avec la raison, plutôt qu'ignoré en silence")

    print(f"\n{'✓ tests transitions OK' if not ko else f'✗ {ko} échec(s)'}")
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
