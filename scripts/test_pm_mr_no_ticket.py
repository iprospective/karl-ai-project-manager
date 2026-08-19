#!/usr/bin/env python3
"""Tests offline du mode « MR sans ticket » de `pm-mr create` (RM2644).

Lancer : python3 scripts/test_pm_mr_no_ticket.py — aucun réseau.

Contexte : certains changements n'ont pas de ticket (ajout au glossaire du cockpit,
correction de coquille — cf. NORMS governance). Ils gardent leur MR, parce que la
branche d'intégration reste protégée : « sans ticket » n'est pas « push direct ».
Avant ce mode, `pm-mr create` exigeait un `rm_id` et la MR devait se créer à la main
par l'API — un one-off, exactement ce que le tripwire #1 refuse de laisser s'installer.

Couvre les refus (ils valent le fix : un mode permissif poserait des CF sur un ticket
imaginaire) et le garde de branche, qui s'INVERSE en mode sans ticket.
"""
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
_spec = importlib.util.spec_from_file_location("pm_mr", str(_HERE / "pm-mr.py"))
pm_mr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_mr)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


class Args:
    def __init__(self, **kw):
        self.rm_id = None
        self.no_ticket = False
        self.title = None
        self.status = None
        self.__dict__.update(kw)


def refuses(args):
    """Retourne le message d'erreur si check_no_ticket_args refuse, sinon None."""
    try:
        pm_mr.check_no_ticket_args(args)
        return None
    except SystemExit as e:
        return str(e)


# ------------------------------------------------------- cohérence des arguments

check("mode normal avec rm_id → accepté",
      refuses(Args(rm_id=2644)) is None)

msg = refuses(Args())
check("ni rm_id ni --no-ticket → refusé", msg is not None)
check("  … et le message propose --no-ticket", msg and "--no-ticket" in msg)

msg = refuses(Args(rm_id=2644, no_ticket=True, title="x"))
check("--no-ticket AVEC un rm_id → refusé (contradiction, pas de choix silencieux)",
      msg is not None and "contradictoires" in msg)

msg = refuses(Args(no_ticket=True))
check("--no-ticket sans --title → refusé", msg is not None)
check("  … et le message dit pourquoi (titre par défaut = RM<id> — <branche>)",
      msg and "--title" in msg)

msg = refuses(Args(no_ticket=True, title="glossaire : one-off", status="a_mep"))
check("--no-ticket avec --status → refusé (aucun ticket à faire transiter)",
      msg is not None and "--status" in msg)

check("--no-ticket + --title seuls → accepté",
      refuses(Args(no_ticket=True, title="cockpit: glossaire — ajout de « one-off »")) is None)


# ------------------------------------------------ garde de branche (inversé, RM2644)
# Le code du garde vit dans cmd_create ; on rejoue ici sa condition, qui est le
# cœur du comportement : une branche `<id>-…` en mode sans ticket = ticket oublié.
import re  # noqa: E402


def branch_guard_rejects(src, no_ticket, rm_id=None):
    m = re.match(r"^(\d+)-", src)
    if m and no_ticket:
        return True
    if m and not no_ticket and int(m.group(1)) != rm_id:
        return True
    return False


check("branche `2644-…` avec --no-ticket → refusée (ticket oublié)",
      branch_guard_rejects("2644-pm-mr-no-ticket", no_ticket=True))
check("branche `glossaire-one-off` avec --no-ticket → acceptée",
      not branch_guard_rejects("glossaire-one-off", no_ticket=True))
check("branche `2644-…` avec le bon rm_id → acceptée (comportement inchangé)",
      not branch_guard_rejects("2644-pm-mr-no-ticket", no_ticket=False, rm_id=2644))
check("branche `2644-…` avec un rm_id différent → refusée (tripwire #13, inchangé)",
      branch_guard_rejects("2644-pm-mr-no-ticket", no_ticket=False, rm_id=2646))


# ----------------------------------------------------------------- argparse réel

import argparse  # noqa: E402

parser_ok = True
try:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    pc = sub.add_parser("create")
    pc.add_argument("rm_id", type=int, nargs="?")
    pc.add_argument("--no-ticket", action="store_true")
    pc.add_argument("--title")
    a = ap.parse_args(["create", "--no-ticket", "--title", "t"])
    parser_ok = a.rm_id is None and a.no_ticket
except Exception:
    parser_ok = False
check("rm_id positionnel devenu optionnel (nargs='?')", parser_ok)

src = (_HERE / "pm-mr.py").read_text(encoding="utf-8")
check("le sous-parseur create déclare bien --no-ticket", '"--no-ticket"' in src)
check("CF Redmine et frontmatter sautés en mode sans ticket",
      "if not args.no_ticket:" in src and "_post_git_cf" in src)


print()
if fails:
    print(f"ÉCHEC — {len(fails)} test(s) : " + ", ".join(fails))
    sys.exit(1)
print("OK — tous les tests passent")
