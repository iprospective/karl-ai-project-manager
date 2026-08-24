#!/usr/bin/env python3
"""Tests RM2763 — pile de refresh : op_refresh (endpoint composite).

Unitaire (sans tmux ni réseau) : parsing des specs, dédup par hash (skipped),
briefs embarqués dans le bloc sessions, retour partiel sur bloc en échec.
Lancer : python3 scripts/test_karl_agent_refresh.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# ── stubs : aucun tmux/fichier — on teste la mécanique composite ────────────
SESSIONS = [{"rm_id": "2763", "state": "idle"},
            {"rm_id": "scratch", "is_ticket": False, "state": "idle"}]
ka._sessions_view = lambda qs, ctx=None: SESSIONS
ka._list_sessions = lambda: SESSIONS
ka._tmux = lambda *a, **k: (0, "", "")
ka.op_tickets_brief = lambda ids: {i: {"found": True, "rm_id": i, "title": "T"} for i in ids}
ka.op_worklog = lambda sid, force=False: {"rm_id": sid, "found": True, "buckets": {}}

# 1. premier appel (hash vide) : les 3 blocs reviennent avec data + hash
r = ka.op_refresh("sessions:,health:,worklog:2763:")
check("3 blocs au premier appel", set(r["blocks"]) == {"sessions", "health", "worklog"})
check("pas de skipped ni d'erreur", r["skipped"] == [] and r["errors"] == {})
check("hash présent par bloc", all(b.get("hash") for b in r["blocks"].values()))
check("sessions : data.sessions transmis", r["blocks"]["sessions"]["data"]["sessions"] == SESSIONS)

# 2. briefs embarqués : seulement les ancrages ticket (rm_id numérique)
briefs = r["blocks"]["sessions"]["data"]["briefs"]
check("briefs : ticket inclus, slug exclu", set(briefs) == {"2763"})

# 3. hash renvoyé → bloc inchangé listé dans skipped, sans payload
h = {k: v["hash"] for k, v in r["blocks"].items()}
r2 = ka.op_refresh(f"sessions:{h['sessions']},health:{h['health']},worklog:2763:{h['worklog']}")
check("tout inchangé → skipped", sorted(r2["skipped"]) == ["health", "sessions", "worklog"])
check("tout inchangé → aucun bloc", r2["blocks"] == {})

# 4. la donnée change → le bloc revient avec un nouveau hash
SESSIONS.append({"rm_id": "2764", "state": "attention"})
r3 = ka.op_refresh(f"sessions:{h['sessions']}")
check("changement → bloc renvoyé", "sessions" in r3["blocks"]
      and r3["blocks"]["sessions"]["hash"] != h["sessions"])

# 5. worklog : sid vide ignoré ; sid avec ':' recomposé (hash = dernier segment)
r4 = ka.op_refresh("worklog:")
check("worklog sans sid ignoré", r4["blocks"] == {} and r4["errors"] == {})
seen = {}
ka.op_worklog = lambda sid, force=False: seen.setdefault("sid", sid) or {"rm_id": sid}
ka.op_refresh("worklog:a:b:")
check("sid multi-segments recomposé", seen["sid"] == "a:b")

# 6. bloc inconnu → errors ; bloc en échec → retour partiel
r5 = ka.op_refresh("bogus:,health:")
check("bloc inconnu en errors", "bogus" in r5["errors"] and "health" in r5["blocks"])
ka.op_worklog = lambda sid, force=False: (_ for _ in ()).throw(RuntimeError("boom"))
r6 = ka.op_refresh("worklog:2763:,health:")
check("échec d'un bloc → partiel", "worklog" in r6["errors"] and "health" in r6["blocks"])

if fails:
    print(f"\n✗ {len(fails)} échec(s)")
    raise SystemExit(1)
print("\nOK — op_refresh (pile de refresh RM2763)")
