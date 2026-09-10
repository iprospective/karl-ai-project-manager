#!/usr/bin/env python3
"""pm-engine-install — installe, met à jour et teste les moteurs d'agents et les serveurs de modèles (RM3069).

Le cockpit ne transmet qu'un **identifiant de recette** et une **action** ; les commandes vivent dans
`pm_engine_recipes` et nulle part ailleurs. Rien de ce que dit le client n'est exécuté (garde-fou 10).
Deux **portées**, au choix explicite : `--scope user` pose l'outil dans l'espace du développeur, sans
aucun privilège ; `--scope system` le pose pour tous les utilisateurs de la machine, donc `sudo`.
La détection ne se fie pas au seul PATH du démon : un outil installé par un utilisateur (opencode dans
`~/.opencode/bin`, un `npm -g` à préfixe personnel) en est absent et serait déclaré à tort manquant.

  pm-engine-install --status [--json]                    l'état : présent, où, quelle version, quelle portée
  pm-engine-install --recipe claude --action install --scope user     installe pour moi seul
  pm-engine-install --recipe claude --action install --scope system   installe pour tout le monde (sudo)
  pm-engine-install --recipe claude --action update      met à jour — refusée si des sessions tournent dessus
  pm-engine-install --recipe ollama --action test        vérifie que l'outil répond
  --dry-run   n'exécute rien et imprime la commande exacte, telle qu'elle serait lancée
  --force     passe outre la garde des sessions en cours (à dire, jamais à supposer)
"""
import argparse
import json
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_engine_recipes as R                       # noqa: E402
try:
    from pm_log import log as _jlog
except ImportError:
    def _jlog(*a, **k): return None


def _sortie(cmd, timeout=20) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or p.stderr or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def sessions_du_moteur(nom: str) -> list:
    """Les sessions tmux qui tournent avec ce moteur — mettre à jour sous leurs pieds les casserait."""
    out = _sortie(["tmux", "list-panes", "-a", "-F", "#{session_name}\t#{pane_current_command}"])
    return sorted({l.split("\t")[0] for l in out.splitlines()
                   if "\t" in l and l.split("\t")[1].strip() == R.recette(nom).get("bin")})


def _homes() -> list:
    """Les homes où chercher : celui du dev visé s'il est donné, sinon le nôtre, plus les autres
    utilisateurs réels de la machine — un outil « absent » l'est souvent seulement du PATH du démon."""
    vus, out = set(), []
    for h in [os.environ.get("PM_TARGET_HOME"), os.path.expanduser("~")]:
        if h and h not in vus:
            vus.add(h); out.append(h)
    try:
        for u in pwd.getpwall():
            if 1000 <= u.pw_uid < 65534 and u.pw_dir not in vus and os.path.isdir(u.pw_dir):
                vus.add(u.pw_dir); out.append(u.pw_dir)
    except OSError:
        pass
    return out


def trouve(nom: str) -> str:
    """Le binaire, dans le PATH puis dans les emplacements usuels. Renvoie un chemin ou une chaîne vide."""
    r = R.recette(nom)
    if not r:
        return ""
    chemin = shutil.which(r["bin"])
    if chemin:
        return chemin
    for home in _homes():
        for rel in (r.get("extra_paths") or []) + R.CHEMINS:
            if rel.startswith("~/"):
                cand = os.path.join(home, rel[2:], r["bin"])
            elif rel.startswith("/"):
                cand = os.path.join(rel, r["bin"])
            else:
                continue
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    return ""


def portee_du_chemin(chemin: str) -> str:
    """`user` si le binaire vit dans un home, `system` sinon. C'est ce qui distingue « installé pour moi »
    de « installé pour tout le monde » — et ce qui dit quelle mise à jour a une chance d'aboutir."""
    if not chemin:
        return ""
    reel = os.path.realpath(chemin)
    for home in _homes():
        if reel.startswith(os.path.realpath(home) + os.sep):
            return "user"
    return "system"


def etat(nom: str) -> dict:
    """Présent ? où, dans quelle portée ? quelle version ? laquelle est disponible ? le service tourne-t-il ?"""
    r = R.recette(nom)
    chemin = trouve(nom) if r else ""
    d = {"id": nom, "kind": r.get("kind", ""), "label": r.get("label", nom), "bin": r.get("bin", ""),
         "installed": bool(chemin), "path": chemin, "scope": portee_du_chemin(chemin),
         "scopes": [s for s in R.PORTEES if s in (r.get("install") or {})] if r else [],
         "version": "", "latest": "", "service": "", "sessions": []}
    if not r:
        return d
    if chemin:
        d["version"] = R.version_de(_sortie([chemin] + list(r["version"][1:])), nom)
        d["sessions"] = sessions_du_moteur(nom)
        if r.get("service"):
            d["service"] = _sortie(r["service"]) or "inconnu"
    if r.get("latest"):
        d["latest"] = R.version_de(_sortie(r["latest"]), nom) or ""
    d["update_available"] = bool(d["version"] and d["latest"] and d["version"] != d["latest"])
    return d


def etats() -> list:
    return [etat(n) for n in sorted(R.RECETTES)]


def execute(nom: str, action: str, dry=False, force=False, portee="user") -> dict:
    cmd = R.commande(nom, action, portee)            # lève si recette, action ou portée est inconnue
    if action == "test":                             # tester, c'est appeler le binaire LÀ OÙ IL EST
        chemin = trouve(nom)
        if not chemin:
            return {"ok": False, "id": nom, "action": action, "scope": portee, "cmd": " ".join(cmd),
                    "error": f"{nom} introuvable — ni dans le PATH, ni dans les emplacements usuels"}
        cmd = [chemin] + cmd[1:]
    if action == "update" and not force:
        vives = sessions_du_moteur(nom)
        if vives:
            return {"ok": False, "id": nom, "action": action, "scope": portee,
                    "cmd": " ".join(cmd), "blocked": vives,
                    "error": f"{len(vives)} session(s) tournent avec {nom} ({', '.join(vives[:4])}) — "
                             "les couper ou relancer avec --force"}
    if dry:
        return {"ok": True, "id": nom, "action": action, "scope": portee, "cmd": " ".join(cmd),
                "dry_run": True}
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    ok = p.returncode == 0
    _jlog("env", "info" if ok else "warn",
          f"{nom} : {action} ({portee}) {'réussie' if ok else 'échouée'}", cmd=" ".join(cmd), rc=p.returncode)
    return {"ok": ok, "id": nom, "action": action, "scope": portee, "cmd": " ".join(cmd), "rc": p.returncode,
            "out": (p.stdout or "").strip()[-1500:], "err": (p.stderr or "").strip()[-800:],
            "etat": etat(nom)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true"); ap.add_argument("--list", action="store_true")
    ap.add_argument("--recipe"); ap.add_argument("--action", choices=R.ACTIONS, default="test")
    ap.add_argument("--scope", choices=R.PORTEES, default="user",
                    help="user = pour le développeur seul (sans privilège) ; system = pour tous (sudo)")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.list:
        print(json.dumps(R.catalogue(), ensure_ascii=False, indent=1)); return 0
    if a.status or not a.recipe:
        st = etats()
        if a.json:
            print(json.dumps(st, ensure_ascii=False, indent=1)); return 0
        for d in st:
            ou = {"user": " (utilisateur)", "system": " (système)"}.get(d["scope"], "")
            etiq = ("installé" + ou + " " + (d["version"] or "?")) if d["installed"] else "absent"
            maj = f" → {d['latest']} disponible" if d.get("update_available") else ""
            svc = f" · service {d['service']}" if d["service"] else ""
            sess = f" · {len(d['sessions'])} session(s)" if d["sessions"] else ""
            print(f"  {d['kind']:7} {d['id']:10} {etiq}{maj}{svc}{sess}")
            if d["installed"]:
                print(f"  {'':7} {'':10} {d['path']}")
        return 0
    try:
        r = execute(a.recipe, a.action, dry=a.dry_run, force=a.force, portee=a.scope)
    except (KeyError, ValueError) as e:
        sys.exit(f"ERREUR : {e}")
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(("✓ " if r["ok"] else "✗ ")
              + f"{r['id']} · {r['action']} · {r.get('scope', '')} · {r['cmd']}")
        if r.get("error"):
            print("  " + r["error"])
        if r.get("out"):
            print("  " + r["out"][-400:].replace("\n", "\n  "))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
