#!/usr/bin/env python3
"""Tests RM3208 (P1) — parité CLI ↔ cockpit : aucune écriture d'état enfermée dans le serveur du cockpit.

Pourquoi : une instance peut tourner sans cockpit. Toute route qui MODIFIE l'état en écrivant elle-même (fichier, conf,
état JSON) sans passer par un script CLI ni par un module que le CLI utilise aussi rend ce geste impossible
hors cockpit — et chaque nouveau panneau pouvait en rouvrir un sans que personne ne le voie.

Règle, vérifiée par analyse syntaxique de `karl-agent.py` (pas de fenêtre de lignes : le handler SEUL) :
- routes POST/PUT/DELETE/PATCH du dispatch HTTP ; appels suivis sur deux niveaux ;
- ÉCRIT : `write_text`, `atomic_write`, `_write_json_atomic`, `os.replace`, `open(…, "w")`, `json.dump`… ;
- DÉLÈGUE : lance un script `pm-*`/`karl-*`/`redmine-*` (`_pm_script`, `_mail_script`, nom de script en
  littéral), ou appelle un module `pm_*` importé par au moins un script CLI `pm-*.py` ;
- une route qui ÉCRIT sans DÉLÉGUER doit figurer dans EXCEPTIONS, avec sa raison ou le ticket qui la traite.

Le test échoue aussi sur une exception PÉRIMÉE (route disparue, ou qui délègue désormais) : la liste ne doit
contenir que ce qui reste à faire, sinon elle cesse d'être lue.

Limite assumée : « délègue à un module partagé » prouve que la logique n'est plus enfermée dans le serveur,
pas qu'un verbe CLI l'expose — la table de couverture de `session-tooling` en tient le compte. Les routes GET
ne sont pas contrôlées (une lecture qui écrit est une anomalie d'une autre nature).
"""
import ast
import re
import sys
from pathlib import Path

S = Path(__file__).resolve().parent
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


TERMINAL = "pilotage des sessions et terminaux supervisés — sans objet sans cockpit"
V2 = "CLI de configuration / consultation — RM3210 (V2)"
#: Routes qui écrivent en direct, admises nommément. Retirer une ligne dès que la route délègue.
EXCEPTIONS = {
    **{f"POST /session-set{s}": TERMINAL for s in ("", "/autostart", "/restart", "/rename", "/rule", "/materialize",
                                                    "/retention", "/move", "/create", "/current", "/restore")},
    "DELETE /session-set": TERMINAL,
    "POST /disposition": "disposition de l'écran du cockpit — préférence d'affichage, sans objet sans cockpit",
    "POST /memdebug": "diagnostic mémoire du démon cockpit",
    "POST /pm/settings": V2 + " : réglages d'instance (T1)",
    "POST /pm/provider-assign": V2 + " : affecter un provider à un projet (T2)",
    "POST /alerts/snooze": V2 + " : reporter une alerte (T5)",
}

src = (S / "karl-agent.py").read_text(encoding="utf-8")
tree = ast.parse(src)
funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
cls_methods = {m.name: m for n in tree.body if isinstance(n, ast.ClassDef) for m in n.body if isinstance(m, ast.FunctionDef)}
cli_mods = set()
for f in S.glob("pm-*.py"):
    try:
        t = ast.parse(f.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    for n in ast.walk(t):
        if isinstance(n, ast.Import):
            cli_mods |= {a.name for a in n.names if a.name.startswith("pm_")}
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("pm_"):
            cli_mods.add(n.module)
SCRIPT_RE = re.compile(r"(^|/)(pm|karl|redmine)-[\w.-]+(\.py)?$|^mmi-pm$")
WRITE_ATTR = {"write_text", "write_bytes", "unlink", "mkdir", "chmod", "chown", "symlink_to", "rmtree", "rename", "touch"}
WRITE_NAME = {"atomic_write", "_write_json_atomic", "_auth_save"}
def aliases(fn):
    al = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith("pm_"): al[a.asname or a.name] = a.name
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("pm_"):
            for a in n.names: al[a.asname or a.name] = n.module
    return al
GLOBAL_AL = aliases(ast.Module(body=[n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))], type_ignores=[]))
def analyse(nodes, depth=0, seen=None):
    seen = seen or set(); deleg, write, why = False, False, []
    al = dict(GLOBAL_AL)
    for nd in nodes: al.update(aliases(nd))
    for nd in nodes:
        for n in ast.walk(nd):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and SCRIPT_RE.search(n.value.strip()):
                deleg = True; why.append(f"script {n.value}")
            if not isinstance(n, ast.Call): continue
            f = n.func
            if isinstance(f, ast.Name):
                if f.id in ("_pm_script", "_mail_script"): deleg = True; why.append(f.id)
                if f.id in WRITE_NAME: write = True; why.append(f"écrit {f.id}")
                if f.id in al and al[f.id] in cli_mods: deleg = True; why.append(f"module CLI {al[f.id]}")
                if f.id == "open" and len(n.args) > 1 and isinstance(n.args[1], ast.Constant) and any(c in str(n.args[1].value) for c in "wa"):
                    write = True; why.append("open w")
                if f.id in funcs and f.id not in seen and depth < 2 and not f.id.startswith(("_send", "_read", "_require", "_check", "_journal", "_jlog")):
                    seen.add(f.id); d2, w2, y2 = analyse([funcs[f.id]], depth + 1, seen)
                    deleg |= d2; write |= w2; why += [f"{f.id}→{y}" for y in y2[:3]]
            elif isinstance(f, ast.Attribute):
                base = f.value.id if isinstance(f.value, ast.Name) else None
                if base in al and al[base] in cli_mods: deleg = True; why.append(f"module CLI {al[base]}.{f.attr}")
                if f.attr in WRITE_ATTR: write = True; why.append(f"écrit .{f.attr}")
                if base == "os" and f.attr in ("replace", "rename", "remove", "unlink", "symlink", "makedirs"): write = True; why.append(f"écrit os.{f.attr}")
                if base == "json" and f.attr == "dump": write = True; why.append("json.dump")
                if base in ("requests",) and f.attr in ("post", "put", "delete", "patch"): write = True; why.append("http " + f.attr)
                if f.attr == "write" and not (isinstance(f.value, ast.Attribute) and f.value.attr == "wfile"): write = True; why.append(".write")
    return deleg, write, why
def route_of(test):
    for n in ast.walk(test):
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) and n.left.id == "path":
            for c in n.comparators:
                if isinstance(c, ast.Constant) and isinstance(c.value, str): return c.value
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "startswith" \
           and isinstance(n.func.value, ast.Name) and n.func.value.id == "path" and n.args and isinstance(n.args[0], ast.Constant):
            return n.args[0].value + "*"
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("match", "fullmatch") and n.args \
           and isinstance(n.args[0], ast.Constant) and len(n.args) > 1 and isinstance(n.args[1], ast.Name) and n.args[1].id == "path":
            return "re:" + n.args[0].value
    return None

def routes():
    out = {}
    for meth in ("do_POST", "do_PUT", "do_DELETE", "do_PATCH"):
        m = cls_methods.get(meth)
        if not m:
            continue
        for n in ast.walk(m):
            if isinstance(n, ast.If):
                r = route_of(n.test)
                key = f"{meth[3:]} {r}" if r else None
                if key and key not in out:
                    out[key] = analyse(n.body)
    return out


def main():
    rs = routes()
    print(f"routes mutantes analysées : {len(rs)}")
    check("le dispatch est bien lu (garde contre une analyse vide)", len(rs) >= 40, len(rs))
    check("les comptes délèguent (pm_accounts)", all(rs.get(k, (False,))[0] for k in ("POST /auth/users",)), rs.get("POST /auth/users"))
    check("le lot délègue (pm_batch)", rs.get("POST /worklog/batch", (False,))[0], rs.get("POST /worklog/batch"))
    interne = {k: why for k, (d, w, why) in rs.items() if w and not d}
    non_admises = {k: v for k, v in interne.items() if k not in EXCEPTIONS}
    check("aucune écriture enfermée dans le cockpit hors exceptions nominatives", not non_admises,
          "; ".join(f"{k} ({', '.join(v[:2])})" for k, v in non_admises.items()))
    disparues = [k for k in EXCEPTIONS if k not in rs]
    check("aucune exception sur une route disparue", not disparues, disparues)
    perimees = [k for k in EXCEPTIONS if k in rs and k not in interne]
    check("aucune exception périmée (la route délègue ou n'écrit plus)", not perimees, perimees)
    print("\n" + ("VERT" if not FAIL else f"ROUGE — {len(FAIL)} échec(s)"))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
