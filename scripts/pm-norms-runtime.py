#!/usr/bin/env python3
"""pm-norms-runtime — produit et contrôle le runtime NORMS, par l'API d'un fournisseur du registre (RM3073).

`norms/runtime/*.md` est la réécriture DENSE des normes, celle que lisent les agents et qui leur est
réinjectée après une compaction (RM3071). C'est donc elle qui les engage. Elle portait « Généré ⇒ ne pas
éditer » alors qu'aucun générateur n'existait : écrite une fois à la main, elle se désynchronisait de ses
sources en silence.

  pm-norms-runtime --check                état : périmé ? ancres perdues ? (exit 1 si non)
  pm-norms-runtime --build KERNEL.md      propose une réécriture, SANS rien remplacer
  pm-norms-runtime --build --all
  pm-norms-runtime --diff [fichier]       ce que la proposition changerait
  pm-norms-runtime --apply [fichier]      remplace, après contrôle des ancres — refusé si une est perdue
  --service openrouter | --instance <nom> | --url … --type …     quel fournisseur appeler
  --model <id>        le modèle (sinon celui de l'instance, sinon LLM_MODEL)
  --force             applique malgré des ancres perdues (à dire, jamais à supposer)

Densifier des normes n'est pas anodin : une règle perdue est un garde-fou perdu, et personne ne s'en
aperçoit avant l'incident. Rien n'est donc remplacé par l'appel : la sortie du modèle atterrit dans
`norms/runtime/.proposed/`, se compare, et ne prend la place de l'existant qu'au `--apply`, contrôle vert.
"""
import argparse
import datetime
import difflib
import hashlib
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_norms_anchors as A                             # noqa: E402
import pm_llm_call as LLM                                # noqa: E402

REPO = HERE.parent
SRC, RT = REPO / "norms" / "src", REPO / "norms" / "runtime"
MANIFEST, PROPOSED = RT / "MANIFEST.yml", RT / ".proposed"

CONSIGNE = """Tu réécris une norme interne pour qu'elle soit lue par un LLM, pas par un humain.

Objectif : le moins de tokens possible, en conservant TOUTE la pertinence, la justesse et l'applicabilité.
Un langage abscon pour un humain n'est pas un problème ; une règle perdue en est un.

Règles absolues :
1. Aucune règle ne disparaît. Si un paragraphe énonce une obligation, une interdiction, une exception ou
   une condition, elle se retrouve dans ta sortie.
2. Les identifiants restent EXACTS et à la lettre : noms de scripts (pm-task-status-update.py), options
   (--list-next), chemins (norms/src/modules/git-mep.md), statuts (a_tester_dev), champs de frontmatter
   (done_ratio), variables d'environnement, noms de champs Redmine. Ne les paraphrase jamais, ne les
   abrège pas : c'est ce qui rend la règle exécutable.
3. Tu peux supprimer : les redites, les transitions, les justifications historiques, les exemples qui
   n'ajoutent pas de cas, la mise en forme décorative. Garde un exemple quand il désambiguïse.
4. Garde la structure en sections courtes et les renvois vers les autres modules.
5. Écris en français, en style télégraphique dense. Pas de préambule, pas de conclusion, pas de méta.

Rends UNIQUEMENT le markdown réécrit, sans bloc de code englobant, sans commentaire sur ton travail."""


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]


def manifeste() -> dict:
    return (yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}).get("files") or {}


def source_de(nom: str, man=None) -> str:
    """Le texte des sources couvertes par un fichier runtime, concaténé dans l'ordre déclaré."""
    e = (man or manifeste()).get(nom) or {}
    return "".join((SRC / s).read_text(encoding="utf-8") for s in (e.get("covers") or []))


def etat(nom: str, man=None) -> dict:
    """Périmé ? des ancres perdues ? — les deux questions qu'on doit pouvoir poser sans appeler personne."""
    man = man or manifeste()
    e = man.get(nom) or {}
    src, cible = source_de(nom, man), RT / nom
    rt = cible.read_text(encoding="utf-8") if cible.is_file() else ""
    sha = _sha(src)
    d = {"file": nom, "exists": bool(rt), "covers": e.get("covers") or [],
         "sha_source": sha, "sha_declared": e.get("sha", ""),
         "stale": bool(e.get("sha")) and e.get("sha") != sha,
         "never_generated": not e.get("sha"),
         "generated": e.get("generated", ""), "model": e.get("model", ""),
         "src_chars": len(src), "rt_chars": len(rt)}
    d["gain"] = (1 - d["rt_chars"] / d["src_chars"]) if d["src_chars"] else 0.0
    return d


def controle(nom: str, texte=None, man=None) -> dict:
    """Les ancres de la source retrouvées dans le texte proposé (ou dans le fichier en place)."""
    man = man or manifeste()
    src = source_de(nom, man)
    rt = texte if texte is not None else ((RT / nom).read_text(encoding="utf-8") if (RT / nom).is_file() else "")
    gardees, total, perdues = A.couverture(src, rt)
    return {"file": nom, "kept": gardees, "total": total, "lost": perdues,
            "ok": not perdues, "rate": (gardees / total) if total else 1.0}


def corpus() -> dict:
    """Le contrôle au niveau du CORPUS : déplacer une règle d'un fichier à l'autre est permis, la perdre non."""
    man = manifeste()
    src = "".join(source_de(n, man) for n in man)
    rt = "".join((RT / n).read_text(encoding="utf-8") for n in man if (RT / n).is_file())
    g, t, perdues = A.couverture(src, rt)
    return {"kept": g, "total": t, "lost": perdues, "ok": not perdues, "rate": (g / t) if t else 1.0}


def genere(nom: str, args, man=None) -> dict:
    """Appelle le fournisseur et DÉPOSE la proposition. Ne remplace rien : c'est `--apply` qui décide."""
    man = man or manifeste()
    src = source_de(nom, man)
    if not src:
        raise KeyError(f"{nom} : aucune source déclarée dans {MANIFEST.name}")
    url, dial, inst, modele = LLM.resout(args.service, args.instance, args.url, args.type_, args.model)
    role = (man.get(nom) or {}).get("role") or ""
    msgs = [{"role": "system", "content": CONSIGNE},
            {"role": "user", "content": (f"Fichier cible : {nom}"
                                         + (f"\nRôle de ce fichier : {role}" if role else "")
                                         + f"\n\n--- SOURCE ---\n{src}")}]
    texte, usage = LLM.chat(msgs, url, dial, LLM.cle_de(inst), modele, max_tokens=args.max_tokens)
    texte = texte.strip()
    if texte.startswith("```"):                 # certains modèles enveloppent malgré la consigne
        texte = texte.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    if not texte:
        raise LLM.LlmError(f"{nom} : le modèle n'a rien rendu")
    PROPOSED.mkdir(parents=True, exist_ok=True)
    (PROPOSED / nom).write_text(texte + "\n", encoding="utf-8")
    ctl = controle(nom, texte, man)
    (PROPOSED / (nom + ".meta.json")).write_text(json.dumps(
        {"file": nom, "model": modele, "instance": inst, "url": url, "usage": usage,
         "sha_source": _sha(src), "generated": datetime.date.today().isoformat(),
         "kept": ctl["kept"], "total": ctl["total"], "lost": ctl["lost"]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return {"file": nom, "model": modele, "usage": usage, "chars": len(texte),
            "src_chars": len(src), "control": ctl}


def applique(nom: str, force=False, man=None) -> dict:
    """Promeut la proposition, si et seulement si aucune ancre n'est perdue."""
    man = man or manifeste()
    prop = PROPOSED / nom
    if not prop.is_file():
        raise FileNotFoundError(f"{nom} : aucune proposition — lance d'abord --build")
    texte = prop.read_text(encoding="utf-8")
    ctl = controle(nom, texte, man)
    if not ctl["ok"] and not force:
        return {"file": nom, "applied": False, "control": ctl,
                "error": f"{len(ctl['lost'])} ancre(s) perdue(s) : " + ", ".join(ctl["lost"][:8])
                         + " — corrige la proposition, relance, ou assume avec --force"}
    (RT / nom).write_text(texte, encoding="utf-8")
    meta = {}
    mp = PROPOSED / (nom + ".meta.json")
    if mp.is_file():
        meta = json.loads(mp.read_text(encoding="utf-8"))
    e = dict(man.get(nom) or {})
    e.update({"sha": _sha(source_de(nom, man)), "generated": meta.get("generated") or datetime.date.today().isoformat(),
              "model": meta.get("model", ""), "kept": ctl["kept"], "total": ctl["total"]})
    man[nom] = e
    _ecrit_manifeste(man)
    prop.unlink(); mp.unlink(missing_ok=True)
    return {"file": nom, "applied": True, "control": ctl}


def _ecrit_manifeste(man: dict):
    """Réécrit le manifeste en gardant son en-tête : c'est un fichier commenté, pas un dépotoir."""
    brut = MANIFEST.read_text(encoding="utf-8")
    entete = brut.split("files:", 1)[0]
    MANIFEST.write_text(entete + "files:\n" + yaml.safe_dump(man, allow_unicode=True, sort_keys=False,
                                                             default_flow_style=False, indent=2).rstrip()
                        .replace("\n", "\n  ").rjust(0) + "\n", encoding="utf-8")
    # yaml.safe_dump rend les clés à plat : on les réindente d'un cran sous `files:`
    t = MANIFEST.read_text(encoding="utf-8")
    lignes = t.split("files:\n", 1)
    corps = "\n".join(("  " + l) if l and not l.startswith("  ") else l for l in lignes[1].splitlines())
    MANIFEST.write_text(lignes[0] + "files:\n" + corps + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true"); ap.add_argument("--build", nargs="?", const="", default=None)
    ap.add_argument("--diff", nargs="?", const="", default=None); ap.add_argument("--apply", nargs="?", const="", default=None)
    ap.add_argument("--all", action="store_true"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--service"); ap.add_argument("--instance"); ap.add_argument("--url")
    ap.add_argument("--type", dest="type_"); ap.add_argument("--model")
    ap.add_argument("--max-tokens", type=int, default=16000); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    man = manifeste()
    cibles = [f for f in man] if (a.all or not (a.build or a.diff or a.apply)) else \
             [x for x in [a.build or a.diff or a.apply] if x]

    if a.build is not None:
        res = []
        for nom in (cibles if (a.all or not a.build) else [a.build]):
            try:
                r = genere(nom, a, man); res.append(r)
                c = r["control"]
                print(f"  {'✓' if c['ok'] else '⚠'} {nom} : {r['src_chars']} → {r['chars']} caractères "
                      f"({100 - 100 * r['chars'] // max(r['src_chars'], 1)} % de moins) · "
                      f"{c['kept']}/{c['total']} ancres · {r['usage'].get('in', 0)}+{r['usage'].get('out', 0)} tokens")
                if c["lost"]:
                    print("      perdues : " + ", ".join(c["lost"][:10]))
            except (KeyError, FileNotFoundError, LLM.LlmError) as e:
                print(f"  ✗ {nom} : {e}")
        print(f"\nPropositions dans {PROPOSED.relative_to(REPO)} — rien n'a été remplacé. "
              f"`--diff` pour voir, `--apply` pour promouvoir.")
        return 0 if res else 1

    if a.diff is not None:
        for nom in (cibles if (a.all or not a.diff) else [a.diff]):
            p = PROPOSED / nom
            if not p.is_file():
                print(f"  · {nom} : aucune proposition"); continue
            ancien = (RT / nom).read_text(encoding="utf-8").splitlines() if (RT / nom).is_file() else []
            print("".join(difflib.unified_diff(ancien, p.read_text(encoding="utf-8").splitlines(),
                                               fromfile=f"runtime/{nom}", tofile=f"proposé/{nom}",
                                               lineterm="", n=1)).replace("\n", "\n") or f"  · {nom} : identique")
        return 0

    if a.apply is not None:
        rc = 0
        for nom in (cibles if (a.all or not a.apply) else [a.apply]):
            try:
                r = applique(nom, a.force, man)
            except FileNotFoundError as e:
                print(f"  · {e}"); continue
            print(("  ✓ " if r["applied"] else "  ✗ ") + nom
                  + (f" appliqué ({r['control']['kept']}/{r['control']['total']} ancres)" if r["applied"]
                     else " : " + r["error"]))
            rc = rc or (0 if r["applied"] else 1)
            man = manifeste()
        return rc

    # --check (par défaut)
    etats = [etat(n, man) for n in man]
    ctls = [controle(n, None, man) for n in man]
    glob = corpus()
    if a.json:
        print(json.dumps({"files": etats, "controls": ctls, "corpus": glob}, ensure_ascii=False, indent=1))
        return 0 if (glob["ok"] and not any(e["stale"] for e in etats)) else 1
    for e, c in zip(etats, ctls):
        quoi = ("absent" if not e["exists"] else
                "PÉRIMÉ (source modifiée)" if e["stale"] else
                "jamais généré" if e["never_generated"] else f"à jour ({e['generated']}, {e['model']})")
        print(f"  {'✓' if (e['exists'] and not e['stale']) else '✗'} {e['file']:22} {quoi:34} "
              f"{100 * e['gain']:.0f} % plus court · {c['kept']}/{c['total']} ancres")
    print(f"\n  corpus : {glob['kept']}/{glob['total']} ancres gardées ({100 * glob['rate']:.0f} %)")
    if glob["lost"]:
        print("  perdues : " + ", ".join(glob["lost"][:15])
              + (f" … et {len(glob['lost']) - 15} autres" if len(glob["lost"]) > 15 else ""))
    ok = glob["ok"] and not any(e["stale"] or not e["exists"] for e in etats)
    print("\n" + ("OK — le runtime couvre ses sources" if ok
                  else "ÉCHEC — le runtime a dérivé de ses sources"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
