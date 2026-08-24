#!/usr/bin/env python3
"""Tests RM2801 — l'étape atteinte par les MR d'un ticket.

Le worklog ne montrait que les MR OUVERTES (`mrs_pending`) : une MR mergée en
sortait sans sortir du store, si bien que « pas de MR » et « MR mergée » se
ressemblaient — alors que l'un demande du travail et l'autre une promotion, puis
un déploiement. La distinction intégration / production n'apparaissait nulle
part, alors que le store la porte (`target`, `state`).

Lancer : python3 scripts/test_karl_agent_mr_stage.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core          # noqa: E402

hermetic_core()

_spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(_spec)
sys.modules["karl_agent"] = ka
_spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def mr(ref, state, target, iid="1", **kw):
    return dict({"ref": ref, "state": state, "target": target, "iid": iid}, **kw)


# — les trois étapes —
st = ka.mr_stage_by_ref([mr("RM1", "opened", "dev")])
check("une MR ouverte : « à merger »", st["RM1"]["stage"] == "open")
st = ka.mr_stage_by_ref([mr("RM1", "merged", "dev")])
check("mergée dans l'intégration", st["RM1"]["stage"] == "integration")
st = ka.mr_stage_by_ref([mr("RM1", "merged", "main")])
check("mergée ailleurs que l'intégration : promue en production",
      st["RM1"]["stage"] == "prod")

# — la cible d'intégration vient de la CONFIG, pas d'une liste en dur —
st = ka.mr_stage_by_ref([mr("RM1", "merged", "integration")], integration="integration")
check("un projet qui nomme autrement sa branche d'intégration est compris",
      st["RM1"]["stage"] == "integration")
st = ka.mr_stage_by_ref([mr("RM1", "merged", "dev")], integration="integration")
check("…et « dev » y devient alors une cible de production",
      st["RM1"]["stage"] == "prod")

# — plusieurs MR : l'étape la plus avancée —
st = ka.mr_stage_by_ref([mr("RM1", "merged", "dev", "1"), mr("RM1", "merged", "main", "2")])
check("deux MR : on affiche la plus avancée", st["RM1"]["stage"] == "prod")
check("…et on dit combien il y en a", st["RM1"]["count"] == 2)
check("…avec le détail de chacune", len(st["RM1"]["mrs"]) == 2)
st = ka.mr_stage_by_ref([mr("RM1", "merged", "main", "2"), mr("RM1", "opened", "dev", "1")])
check("l'ordre d'arrivée ne change pas le verdict", st["RM1"]["stage"] == "prod")

# — ce qui ne compte pas —
check("une MR fermée sans merge ne franchit rien",
      ka.mr_stage_by_ref([mr("RM1", "closed", "dev")]) == {})
check("une MR sans ticket ne se rattache à rien",
      ka.mr_stage_by_ref([mr("", "merged", "dev")]) == {})
# Constaté sur les worklogs réels : une MR de PROMOTION (dev → main) est
# enregistrée `ref: "sans ticket"` — elle emporte tout l'intégration et
# n'appartient à aucun ticket. La ranger sous cette clé créait une entrée que
# rien n'affiche, dans un payload rendu à chaque rafraîchissement.
check("une MR de promotion (« sans ticket ») ne crée pas d'entrée fantôme",
      ka.mr_stage_by_ref([mr("sans ticket", "merged", "main")]) == {})
check("une référence qui n'est pas un ticket est ignorée",
      ka.mr_stage_by_ref([mr("chantier-libre", "merged", "dev")]) == {})
check("la casse de la référence est tolérée",
      "rm7" in ka.mr_stage_by_ref([mr("rm7", "merged", "dev")]))
check("aucune MR → aucune étape", ka.mr_stage_by_ref([]) == {})
check("liste absente tolérée", ka.mr_stage_by_ref(None) == {})
check("un état inconnu est traité comme mergé, pas ignoré",
      ka.mr_stage_by_ref([mr("RM1", "bizarre", "dev")])["RM1"]["stage"] == "integration")

# — l'URL suivie est celle de l'étape affichée —
st = ka.mr_stage_by_ref([mr("RM1", "merged", "dev", "1", url="U-dev"),
                         mr("RM1", "merged", "main", "2", url="U-prod")])
check("le lien mène à la MR de l'étape affichée", st["RM1"]["url"] == "U-prod")

# — la branche d'intégration est lue en configuration —
check("la branche d'intégration par défaut est celle du système",
      ka._integration_branch() == "dev")

print()
if fails:
    print(f"ÉCHEC — {len(fails)} contrôle(s) : " + " · ".join(fails))
    sys.exit(1)
print("OK — étape de MR par ticket (ouverte / intégration / production)")
