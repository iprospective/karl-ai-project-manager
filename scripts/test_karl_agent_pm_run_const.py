#!/usr/bin/env python3
"""Tests RM2668 — catalogue de commandes : arg `const` + entrées « mail ».

Unitaire, sans réseau : un flag `const` est imposé par le catalogue (jamais fourni
ni négocié par le client), les entrées mail pointent un script réel, et la relève
n'expose pas d'action destructive (--mark-seen) depuis le cockpit.

Lancer : python3 scripts/test_karl_agent_pm_run_const.py
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


cmds = {c["name"]: c for c in ka._PM_COMMANDS_DEFAULT}

check("commande mail-fetch au catalogue", "mail-fetch" in cmds)
check("commande mail-queue au catalogue", "mail-queue" in cmds)

fetch, queue = cmds.get("mail-fetch", {}), cmds.get("mail-queue", {})
check("relève en lecture (pas de mutation annoncée)", fetch.get("mutate") is False)
check("scripts existants",
      all((HERE / c["script"]).is_file() for c in (fetch, queue) if c.get("script")))
check("script conforme à l'allowlist",
      all(ka._PM_SCRIPT_RE.match(c["script"]) for c in (fetch, queue) if c.get("script")))
check("aucune action destructive exposée (--mark-seen absent)",
      all(a.get("flag") != "--mark-seen" for a in fetch.get("args") or []))

qargs = queue.get("args") or []
check("mail-queue impose --queue", any(a.get("const") and a["flag"] == "--queue" for a in qargs))

# — construction d'argv : le flag const est ajouté sans être demandé —
argv = []


def fake_run(cmd, **kw):
    argv.extend(cmd)

    class R:
        returncode, stdout, stderr = 0, "", ""
    return R()


ka.subprocess.run = fake_run
res = ka.op_pm_run({"name": "mail-queue"})
check("op_pm_run renvoie un résultat", isinstance(res, dict))
check("argv porte --queue", "--queue" in argv)
check("argv sans arg parasite", argv[-1] == "--queue" and argv[-2].endswith("karl-mail-fetch.py"))

# — const positionnel : la sous-commande précède ses arguments (RM2702) —
argv.clear()
ka.op_pm_run({"name": "contact-list", "args": {"client": "calyclay"}})
check("const positionnel en tête", argv[-2:] == ["list", "calyclay"])
argv.clear()
ka.op_pm_run({"name": "contact-add", "args": {"client": "demo", "last_name": "Dupont",
                                              "phone": "+33 6 12 34 56 78"}})
check("sous-commande add avant le client",
      argv.index("add") < argv.index("demo"))
check("téléphone transmis tel quel", "+33 6 12 34 56 78" in argv)
check("contact-add annoncé comme mutation",
      cmds["contact-add"]["mutate"] is True)

# — un client ne peut pas fournir (ni retirer) un arg const —
try:
    ka.op_pm_run({"name": "mail-queue", "args": {"queue": False}})
    refused = False
except ka.ApiError as e:
    refused = e.code == 400
check("arg const fourni par le client → refusé", refused)

# — les args normaux passent toujours —
argv.clear()
ka.op_pm_run({"name": "mail-fetch", "args": {"days": 7, "dry_run": True}})
check("args normaux transmis", "--days" in argv and "7" in argv and "--dry-run" in argv)

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
