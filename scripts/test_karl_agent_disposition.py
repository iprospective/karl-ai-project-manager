#!/usr/bin/env python3
"""Tests RM2515 — disposition manuelle d'une session (à traiter / parké / terminé).

Unitaire (sans tmux ni réseau) : op_disposition pose/efface/valide dans
keys/<sid>.json (STATE_DIR), et _record_key préserve la disposition sur réécriture.
Lancer : python3 scripts/test_karl_agent_disposition.py
"""
import importlib.util
import pathlib
import sys
import tempfile

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


def expect_api(code, fn, name):
    try:
        fn()
        check(name, False)
    except ka.ApiError as e:
        check(name, e.code == code)


# STATE_DIR isolé
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2515-"))
ka.STATE_DIR = tmp
ka.SESS_DIR = tmp / "sessions"


def disp_of(sid):
    key = f"RM{sid}" if ka._is_ticket_sid(sid) else sid
    return (ka._read_json_file(tmp / "keys" / f"{key}.json") or {}).get("disposition")


# ancre une session (crée keys/RM42.json)
ka._record_key("42", "claude", "sid-1", "/w")
check("keys/ créé sans disposition par défaut", disp_of("42") is None)

# pose « parké »
out = ka.op_disposition({"rm_id": "42", "disposition": "parke"})
check("op renvoie la disposition", out["disposition"] == "parke")
check("parké persisté dans keys/", disp_of("42") == "parke")

# _record_key (refresh/reprise) préserve la disposition (comme model)
ka._record_key("42", "claude", "sid-1", "/w")
check("disposition préservée après _record_key", disp_of("42") == "parke")

# « terminé »
ka.op_disposition({"rm_id": "42", "disposition": "termine"})
check("terminé persisté", disp_of("42") == "termine")

# « a_traiter » (défaut) efface la marque
ka.op_disposition({"rm_id": "42", "disposition": "a_traiter"})
check("a_traiter efface la marque", disp_of("42") is None)

# vide efface aussi
ka.op_disposition({"rm_id": "42", "disposition": "parke"})
ka.op_disposition({"rm_id": "42", "disposition": ""})
check("vide efface la marque", disp_of("42") is None)

# slug (session non-ticket)
ka._record_key("mon-slug", "shell", "sid-2", "/w")
ka.op_disposition({"rm_id": "mon-slug", "disposition": "termine"})
check("slug : disposition posée", disp_of("mon-slug") == "termine")

# — gardes —
expect_api(400, lambda: ka.op_disposition({"rm_id": "42", "disposition": "n_importe_quoi"}),
           "disposition invalide → 400")
expect_api(400, lambda: ka.op_disposition({"disposition": "parke"}), "rm_id manquant → 400")
expect_api(404, lambda: ka.op_disposition({"rm_id": "9999", "disposition": "parke"}),
           "session sans entrée keys/ → 404")

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests disposition RM2515 passent")
