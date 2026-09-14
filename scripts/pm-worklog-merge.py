#!/usr/bin/env python3
"""pm-worklog-merge — reprendre un worklog de session resté à l'ancien emplacement (RM2992).

Le déplacement des données vers `var/` a copié les worklogs, puis le démon a continué d'écrire dans
l'ANCIEN tant qu'il n'avait pas redémarré. Au redémarrage il a repris le fichier copié — sans ce qui
avait été écrit entre-temps. Les sessions actives ce jour-là ont donc perdu de vue une partie de leur
travail : 83 tickets devenus 2, par exemple.

Rien n'est effacé : les deux fichiers existent, il faut les recoller.

  pm-worklog-merge --list            ce qui manque, session par session
  pm-worklog-merge --all             recolle tout ce qui est en retard
  pm-worklog-merge <session-id>      une seule
  --dry-run                          montre sans écrire

La fusion garde TOUT : une entrée présente des deux côtés est complétée, jamais remplacée par la plus
pauvre. Une sauvegarde est posée avant chaque écriture — on ne répare pas une perte par une autre.
"""
import argparse
import datetime
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_stores   # noqa: E402  RM2992 : une seule résolution des stores

#: identité d'une entrée, par collection — ce qui permet de dire « c'est la même »
CLES = {
    "items": lambda e: str(e.get("ref") or e.get("id")),
    "requests": lambda e: str(e.get("ts", "")) + str(e.get("text", ""))[:60],
    "mrs": lambda e: str(e.get("iid") or e.get("url")),
    "notifications": lambda e: str(e.get("ts", "")) + str(e.get("message", ""))[:40],
}


def ancien_dir() -> Path:
    # RM2992 : le chemin d'AVANT le déplacement — figé ici, c'est son rôle (on vient le vider).
    return Path(os.environ.get("PM_WORKLOG_OLD_DIR") or pm_stores.WORKLOG_LEGACY).expanduser()


def nouveau_dir() -> Path:
    """Le dossier RÉEL des worklogs — celui du core qui tourne, pas celui d'un clone de dev.

    `PMConfig.load().pm_dir` rend la racine d'où l'on LANCE : depuis un worktree de développement, il
    pointe un `var/` vide, et l'outil croirait qu'il n'y a rien à reprendre. `PM_CORE_DIR` d'abord, donc :
    c'est déjà la variable qui désigne le core canonique partout ailleurs."""
    d = os.environ.get("PM_WORKLOG_DIR")
    if d:
        return Path(d)
    core = os.environ.get("PM_CORE_DIR")
    if core:
        return Path(core) / "var" / pm_stores.WORKLOG_SUB
    # RM2992 : la résolution vient de `pm_stores`, jamais recopiée — recopiée, elle avait déjà
    # divergé ici (un repli vers `~/.local/state/karl-agent/session-worklogs`, qui n'a jamais existé).
    return pm_stores.worklog_dir()


def _lire(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compte(d: dict) -> dict:
    return {k: len(d.get(k) or []) for k in CLES if isinstance(d.get(k), list)}


def fusionne(a: dict, b: dict) -> dict:
    """`a` = l'ancien (l'historique), `b` = le courant. Le courant complète, il n'ampute pas."""
    out = dict(a)
    for cle, idf in CLES.items():
        if not (isinstance(a.get(cle), list) or isinstance(b.get(cle), list)):
            continue
        lignes, vus = [], {}
        for src in (a.get(cle) or [], b.get(cle) or []):
            for e in src if isinstance(src, list) else []:
                if not isinstance(e, dict):
                    continue
                k = idf(e)
                if k in vus:
                    lignes[vus[k]].update({x: y for x, y in e.items() if y not in (None, "")})
                else:
                    vus[k] = len(lignes); lignes.append(dict(e))
        for i, e in enumerate(lignes, 1):
            e["id"] = i
        out[cle] = lignes
    for cle in set(a) | set(b):
        if cle in CLES or cle in ("session_id", "title", "updated"):
            continue
        va, vb = a.get(cle), b.get(cle)
        out[cle] = {**va, **vb} if isinstance(va, dict) and isinstance(vb, dict) else (vb if vb not in (None, [], {}) else va)
    out["session_id"] = b.get("session_id") or a.get("session_id")
    out["title"] = b.get("title") or a.get("title")
    out["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    return out


def en_retard() -> list:
    """[(sid, compte après fusion, compte courant)] pour les sessions où la fusion APPORTERAIT quelque chose.

    On compare ce que la fusion donnerait, pas deux comptes bruts : l'ancien fichier peut porter des
    doublons que la fusion écarte, et comparer les totaux signalerait alors un retard qui n'existe pas —
    un outil de réparation qui crie sans raison n'est plus lu."""
    out = []
    for f in sorted(ancien_dir().glob("*.json")):
        a = _lire(f)
        g = nouveau_dir() / f.name
        b = _lire(g) if g.exists() else {}
        cf, cb = compte(fusionne(a, b)), compte(b)
        if any(cf.get(k, 0) > cb.get(k, 0) for k in cf):
            out.append((f.stem, cf, cb))
    return out


def repare(sid: str, dry=False) -> dict:
    a_p, b_p = ancien_dir() / f"{sid}.json", nouveau_dir() / f"{sid}.json"
    if not a_p.is_file():
        raise FileNotFoundError(f"aucun worklog à l'ancien emplacement pour {sid}")
    a, b = _lire(a_p), _lire(b_p)
    f = fusionne(a, b)
    avant, apres = compte(b), compte(f)
    if dry:
        return {"sid": sid, "avant": avant, "apres": apres, "dry_run": True}
    b_p.parent.mkdir(parents=True, exist_ok=True)
    if b_p.exists():
        shutil.copy2(b_p, b_p.with_suffix(".json.bak-merge"))
    b_p.write_text(json.dumps(f, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"sid": sid, "avant": avant, "apres": apres}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sid", nargs="?"); ap.add_argument("--list", action="store_true")
    ap.add_argument("--all", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.list or not (a.sid or a.all):
        retard = en_retard()
        if not retard:
            print("✓ aucun worklog en retard : le courant a tout ce que l'ancien avait"); return 0
        for sid, ca, cb in retard:
            manque = ", ".join(f"{k} {cb.get(k, 0)}→{ca[k]}" for k in ca if ca[k] > cb.get(k, 0))
            print(f"  ✗ {sid[:12]} : {manque}")
        print(f"\n{len(retard)} session(s) à recoller → pm-worklog-merge --all")
        return 1
    cibles = [s for s, _, _ in en_retard()] if a.all else [a.sid]
    for sid in cibles:
        try:
            r = repare(sid, a.dry_run)
        except FileNotFoundError as e:
            print(f"  · {e}"); continue
        chg = ", ".join(f"{k} {r['avant'].get(k, 0)}→{r['apres'][k]}" for k in r["apres"]
                        if r["apres"][k] != r["avant"].get(k, 0)) or "rien à reprendre"
        print(("[dry-run] " if a.dry_run else "✓ ") + f"{sid[:12]} : {chg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
