#!/usr/bin/env python3
"""pm-core-gitignore — garantit qu'un dépôt de données PM n'emporte pas de secret (RM3371).

Le `.mmi-pm/` d'un projet est l'endroit où l'on a naturellement envie de déposer la conf de ce
projet — donc ses secrets. Aucun des 52 dépôts de données ne les ignorait : un `.env` posé là
partait au dépôt au premier `git add`, et un secret commité reste dans l'historique même
supprimé ensuite.

Le fichier posé est MINIMAL, et c'est volontaire : un `.gitignore` qui en fait trop finit par
masquer un fichier qu'on cherchait à versionner, et on le désactive. Ici, les fichiers
d'environnement seulement — en laissant passer un `.env.example`, car un modèle SANS valeur est
utile ; c'est la valeur qui ne doit pas partir.

  pm-core-gitignore --check            état de tous les dépôts (exit 1 s'il en manque un)
  pm-core-gitignore --apply            pose ce qui manque (idempotent)
  pm-core-gitignore --project E/P      un seul projet
  --json

Un `.gitignore` déjà présent est COMPLÉTÉ, jamais remplacé : il appartient au projet, pas à
cet outil.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig                       # noqa: E402

#: En-tête qui signe notre bloc, pour le reconnaître et ne pas le poser deux fois.
MARQUE = "# — secrets : jamais dans un dépôt de données PM (RM3371) —"

BLOC = MARQUE + """
.env
.env.*
!.env.example
"""


def regles_manquantes(contenu):
    """Lignes de notre bloc absentes du `.gitignore` existant. PURE.

    On compare LIGNE À LIGNE plutôt que de chercher notre en-tête : un projet a pu écrire
    `.env` de lui-même, et lui rajouter un bloc qui répète la même règle ne sert personne.
    """
    presentes = set()
    for ligne in (contenu or "").splitlines():
        l = ligne.strip()
        if l and not l.startswith("#"):
            presentes.add(l)
    return [l for l in (".env", ".env.*", "!.env.example") if l not in presentes]


def bloc_a_ajouter(contenu, manquantes):
    """Texte à APPENDRE (vide si rien à faire). PURE — c'est elle que les tests verrouillent."""
    if not manquantes:
        return ""
    prefixe = "" if not contenu else ("" if contenu.endswith("\n") else "\n")
    return prefixe + "\n" + MARQUE + "\n" + "\n".join(manquantes) + "\n"


#: Suivi DÉLIBÉRÉMENT : un modèle sans valeur documente la conf attendue.
def suivis(repo: Path):
    """Fichiers d'environnement DÉJÀ suivis : le `.gitignore` ne couvre PAS un fichier déjà
    indexé, et c'est exactement le cas qui fait fuiter. `.env.example` est exclu — le signaler
    produirait une alerte permanente sur le fichier qu'on autorise, et une alerte permanente
    finit par ne plus être lue."""
    r = subprocess.run(["git", "-C", str(repo), "ls-files", ".env", ".env.*"],
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines()
            if l.strip() and Path(l.strip()).name != ".env.example"]


def racine_depot(chemin: Path):
    r = subprocess.run(["git", "-C", str(chemin), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def _modifie(racine: Path) -> bool:
    """Le `.gitignore` de ce dépôt diffère-t-il de ce qui est versionné ?"""
    r = subprocess.run(["git", "-C", str(racine), "status", "--porcelain", "--", ".gitignore"],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def _committer(racine: Path):
    """Committe le seul `.gitignore` et pousse. Rend un état lisible, n'échoue jamais en dur :
    un dépôt injoignable ne doit pas empêcher les 51 autres d'être protégés."""
    msg = ("chore: ignorer les fichiers d'environnement (RM3371)\n\n"
           "Un `.env` déposé dans le dépôt de données d'un projet — l'endroit où l'on a\n"
           "naturellement envie de mettre sa conf — partait au dépôt au premier `git add`.\n"
           "Aucun des 53 dépôts ne l'ignorait. `.env.example` reste autorisé : un modèle sans\n"
           "valeur documente la conf attendue, c'est la valeur qui ne doit pas partir.\n")
    add = subprocess.run(["git", "-C", str(racine), "add", ".gitignore"],
                         capture_output=True, text=True)
    if add.returncode != 0:
        return "add refusé : " + (add.stderr or "").strip()[:80]
    com = subprocess.run(["git", "-C", str(racine), "commit", "-m", msg],
                         capture_output=True, text=True)
    if com.returncode != 0:
        return "rien à committer" if "nothing" in (com.stdout + com.stderr) else \
               "commit refusé : " + (com.stderr or com.stdout).strip()[:80]
    psh = subprocess.run(["git", "-C", str(racine), "push", "origin", "HEAD"],
                         capture_output=True, text=True, timeout=120)
    return "committé et poussé" if psh.returncode == 0 else \
           "committé, push refusé : " + (psh.stderr or "").strip().splitlines()[-1][:80]


def projets(cfg, filtre=None):
    for ent, proj, _ in cfg.iter_projects():
        if filtre and f"{ent}/{proj}" != filtre:
            continue
        d = cfg.path("tasks_dir", entity=ent, project=proj).parent
        yield ent, proj, d


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--commit", action="store_true",
                    help="committe et pousse le .gitignore posé, dépôt par dépôt (avec --apply)")
    ap.add_argument("--project", help="entity/project")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not (args.check or args.apply):
        ap.error("--check ou --apply")

    cfg = PMConfig.load()
    etat = []
    for ent, proj, d in projets(cfg, args.project):
        racine = racine_depot(d)
        if racine is None:
            etat.append({"projet": f"{ent}/{proj}", "statut": "hors dépôt git"})
            continue
        gi = racine / ".gitignore"
        contenu = gi.read_text(encoding="utf-8") if gi.is_file() else ""
        manquantes = regles_manquantes(contenu)
        deja = suivis(racine)
        item = {"projet": f"{ent}/{proj}", "depot": str(racine),
                "manquantes": manquantes, "suivis": deja,
                "statut": "ok" if not manquantes else "à compléter"}
        if manquantes and args.apply:
            # Un dépôt non inscriptible (la PROD PM est root) ne doit PAS arrêter les 52 autres :
            # une passe de sécurité qui s'interrompt au premier obstacle ne sécurise rien.
            try:
                ajout = bloc_a_ajouter(contenu, manquantes)
                gi.write_text(contenu + ajout, encoding="utf-8")
                item["statut"] = "posé"
            except OSError as exc:
                item["statut"] = "non inscriptible"
                item["erreur"] = f"{exc.__class__.__name__}: {exc}"
        # On committe dès que le fichier DIFFÈRE de ce qui est versionné — pas seulement quand
        # on vient de l'écrire : une passe interrompue laisse des fichiers posés mais non
        # committés, et la reprise doit les rattraper.
        if args.commit and item["statut"] in ("posé", "ok") and _modifie(racine):
            # `git add` du SEUL .gitignore : ces dépôts sont partagés et souvent sales,
            # emporter le travail en cours de quelqu'un d'autre serait pire que le trou qu'on
            # bouche (garde-fou 2 : jamais `git add .`).
            item["git"] = _committer(racine)
        etat.append(item)

    # Un dépôt peut être partagé par plusieurs projets : on ne le compte qu'une fois.
    vus, uniques = set(), []
    for i in etat:
        cle = i.get("depot") or i["projet"]
        if cle in vus:
            continue
        vus.add(cle)
        uniques.append(i)

    if args.json:
        print(json.dumps(uniques, ensure_ascii=False, indent=2))
    else:
        for i in uniques:
            if i["statut"] != "ok":
                print(f"  {i['statut']:12} {i['projet']}"
                      + (f"  (déjà suivis : {', '.join(i['suivis'])})" if i.get("suivis") else ""))
        reste = [i for i in uniques if i["statut"] == "à compléter"]
        bloques = [i for i in uniques if i["statut"] == "non inscriptible"]
        fuite = [i for i in uniques if i.get("suivis")]
        print(f"\n{len(uniques)} dépôt(s) — {len(reste)} à compléter, "
              f"{len(bloques)} non inscriptible(s), "
              f"{len(fuite)} avec un fichier d'environnement DÉJÀ SUIVI")
        for i in uniques:
            if i.get("git"):
                print(f"  {i['git'][:60]:60} {i['projet']}")
        for b in bloques:
            print(f"  ⚠ {b['projet']} : {b.get('erreur', '')} — à poser par son propriétaire")
        if fuite:
            print("⚠ un fichier déjà suivi reste suivi malgré le .gitignore : "
                  "`git rm --cached` puis vérifier l'historique")
    return 1 if any(i["statut"] == "à compléter" for i in uniques) else 0


if __name__ == "__main__":
    sys.exit(main())
