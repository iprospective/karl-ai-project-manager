#!/usr/bin/env python3
"""Tests RM2793 — le compteur de silence ignore ce que l'agent écrit tout seul.

RM2787 mesurait le silence d'une session avec `#{session_activity}` de tmux, qui
compte TOUTE écriture au terminal. Or Claude Code en produit sans qu'aucune
action n'ait eu lieu : la ligne « ※ recap: … » affichée quand la session reste
sans réponse (`system` / `away_summary` au transcript). Le compteur retombait à
zéro et la session paraissait active — l'indicateur mentait dans le sens le plus
coûteux, en rendant invisible une session à relancer.

Lancer : python3 scripts/test_karl_agent_last_msg.py
"""
import importlib.util
import json
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


def j(**kw):
    return json.dumps(kw)


import datetime                                                     # noqa: E402

T1 = "2026-08-22T10:00:00.000Z"      # vrai message
T2 = "2026-08-22T12:00:00.000Z"      # récapitulatif automatique, plus tard
# Calculé, pas codé en dur : une constante fausse ferait échouer les tests sans
# rien dire du code testé.
EPOCH_T1 = int(datetime.datetime.fromisoformat(T1.replace("Z", "+00:00")).timestamp())

# — le cas fondateur : un recap postérieur ne doit pas primer —
lignes = [
    j(type="user", timestamp=T1, message={"role": "user"}),
    j(type="system", subtype="away_summary", timestamp=T2, content="Fil…", isMeta=True),
]
ts = ka.last_message_ts(lignes)
check("un « away_summary » ne compte pas comme action", ts == EPOCH_T1)

check("…même sans isMeta (c'est le TYPE qui décide)",
      ka.last_message_ts([j(type="user", timestamp=T1),
                          j(type="system", subtype="away_summary", timestamp=T2)]) == EPOCH_T1)

# — les métadonnées non plus —
for meta in ("ai-title", "mode", "permission-mode", "atis-latch", "last-prompt",
             "file-history-snapshot", "attachment"):
    check(f"« {meta} » ne compte pas",
          ka.last_message_ts([j(type="user", timestamp=T1),
                              j(type=meta, timestamp=T2)]) == EPOCH_T1)

# — ni les hooks, ni les sous-agents —
check("un message marqué isMeta (hook, rappel système) ne compte pas",
      ka.last_message_ts([j(type="user", timestamp=T1),
                          j(type="user", timestamp=T2, isMeta=True)]) == EPOCH_T1)
check("un message de sous-agent ne compte pas comme activité du fil principal",
      ka.last_message_ts([j(type="user", timestamp=T1),
                          j(type="assistant", timestamp=T2, isSidechain=True)]) == EPOCH_T1)

# — ce qui compte, en revanche —
check("une réponse de l'agent compte",
      ka.last_message_ts([j(type="user", timestamp=T1),
                          j(type="assistant", timestamp=T2)]) > EPOCH_T1)
check("une question de l'humain compte",
      ka.last_message_ts([j(type="assistant", timestamp=T1),
                          j(type="user", timestamp=T2)]) > EPOCH_T1)

# — robustesse : un transcript est lu pendant qu'il s'écrit —
check("une ligne tronquée est enjambée, pas fatale",
      ka.last_message_ts(['{"type":"user","timestamp":"' + T1 + '"}',
                          '{"type":"assistant","timesta']) == EPOCH_T1)
check("une ligne vide aussi",
      ka.last_message_ts(["", j(type="user", timestamp=T1), "  "]) == EPOCH_T1)
check("un horodatage illisible est ignoré",
      ka.last_message_ts([j(type="user", timestamp=T1),
                          j(type="user", timestamp="pas-une-date")]) == EPOCH_T1)
check("un message sans horodatage est ignoré",
      ka.last_message_ts([j(type="user", timestamp=T1), j(type="user")]) == EPOCH_T1)

# — rien d'exploitable : None, pour que l'appelant retombe sur l'activité tmux —
check("aucun vrai message → None (repli sur tmux, pas un vide)",
      ka.last_message_ts([j(type="system", subtype="away_summary", timestamp=T2)]) is None)
check("liste vide → None", ka.last_message_ts([]) is None)
check("liste absente → None", ka.last_message_ts(None) is None)

# — la lecture reste bornée —
check("la fin de fichier lue est bornée", ka.LAST_MSG_TAIL_BYTES <= 512 * 1024)
check("seuls user/assistant sont retenus", set(ka.LAST_MSG_TYPES) == {"user", "assistant"})

print()
if fails:
    print(f"ÉCHEC — {len(fails)} contrôle(s) : " + " · ".join(fails))
    sys.exit(1)
print("OK — dernier message réel (recap et métadonnées exclus)")
