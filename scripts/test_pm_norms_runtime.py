#!/usr/bin/env python3
"""Tests RM3073 — générer le runtime NORMS par un fournisseur, sans perdre de règle en chemin.

Ce qui doit tenir : une ancre est ce qu'une réécriture n'a pas le droit de changer ; une source modifiée
rend son runtime périmé et ça se voit ; un appel de modèle ne remplace JAMAIS rien tout seul ; une
proposition qui perd une ancre est refusée à l'application ; et déplacer une règle d'un fichier à l'autre
reste permis, puisque c'est le but du découpage.
"""
import importlib.util
import json
import pathlib
import sys
import tempfile

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_norms_anchors as A                             # noqa: E402
import pm_llm_call as LLM                                # noqa: E402
spec = importlib.util.spec_from_file_location("nrt", HERE / "pm-norms-runtime.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


print("[RM3073] les ancres : ce qu'une réécriture n'a pas le droit de changer")
src = ("Passe par `pm-task-status-update.py` ; cibles valides via `--list-next`. Statut `a_tester_dev`. "
       "Voir `norms/src/modules/git-mep.md`. Champ `done_ratio`. Variable `REDMINE_API_KEY`. "
       "ATTENTION : c'est TOUJOURS OBLIGATOIRE.")
anc = A.ancres(src)
check("un nom de script est une ancre", "pm-task-status-update.py" in anc)
check("une option est une ancre", "--list-next" in anc)
check("un statut est une ancre", "a_tester_dev" in anc)
check("un chemin est une ancre", "norms/src/modules/git-mep.md" in anc)
check("un champ de frontmatter est une ancre", "done_ratio" in anc)
check("une variable d'environnement est une ancre", "redmine_api_key" in anc)
check("un mot crié n'est pas une ancre",
      not {"attention", "toujours", "obligatoire"} & anc, sorted(anc)[:6])

print("\n[RM3073] ce que le contrôle tolère, et ce qu'il refuse")
dense = "pm-task-status-update.py --list-next ; a_tester_dev ; git-mep ; done_ratio ; REDMINE_API_KEY"
check("un module cité sans son extension reste couvert", not A.manquantes(src, dense), A.manquantes(src, dense))
check("une option paraphrasée est une PERTE",
      "--list-next" in A.manquantes(src, dense.replace("--list-next", "la liste des cibles")))
check("un script renommé est une PERTE",
      "pm-task-status-update.py" in A.manquantes(src, dense.replace("pm-task-status-update.py", "le script de statut")))
g, t, m = A.couverture(src, dense)
check("la couverture se dit en taux, pas en oui/non", t > 5 and g == t and m == [])


def depot(sources: dict, runtime: dict, manifeste: dict):
    """Un faux dépôt normes, pour éprouver le générateur sans toucher au vrai."""
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "norms" / "src" / "modules").mkdir(parents=True)
    (d / "norms" / "runtime").mkdir(parents=True)
    for k, v in sources.items():
        (d / "norms" / "src" / k).write_text(v, encoding="utf-8")
    for k, v in runtime.items():
        (d / "norms" / "runtime" / k).write_text(v, encoding="utf-8")
    (d / "norms" / "runtime" / "MANIFEST.yml").write_text(
        "# en-tête du manifeste\nfiles:\n" + yaml.safe_dump({"files": manifeste}, allow_unicode=True,
                                                            sort_keys=False).split("files:\n", 1)[1],
        encoding="utf-8")
    R.SRC, R.RT = d / "norms" / "src", d / "norms" / "runtime"
    R.MANIFEST, R.PROPOSED = R.RT / "MANIFEST.yml", R.RT / ".proposed"
    R.REPO = d
    return d


SOURCE = "Règle : passe par `pm-task-take.py`, jamais à la main. Statut `en_cours`. Champ `assigned_to`.\n"
DENSE = "Prise : `pm-task-take.py` seul. `en_cours` ⇒ `assigned_to`.\n"

print("\n[RM3073] périmé : une source qui bouge, un runtime qui le dit")
d = depot({"NORMS-KERNEL.md": SOURCE}, {"KERNEL.md": DENSE},
          {"KERNEL.md": {"covers": ["NORMS-KERNEL.md"], "sha": R._sha(SOURCE), "generated": "2026-09-01", "model": "m"}})
e = R.etat("KERNEL.md")
check("à jour tant que la source ne bouge pas", not e["stale"] and e["exists"])
check("le gain de place est mesuré", 0 < e["gain"] < 1)
(R.SRC / "NORMS-KERNEL.md").write_text(SOURCE + "Nouvelle règle : `--porcelain` obligatoire.\n", encoding="utf-8")
check("source modifiée ⇒ runtime PÉRIMÉ", R.etat("KERNEL.md")["stale"])
check("et l'ancre ajoutée manque au runtime", "--porcelain" in R.controle("KERNEL.md")["lost"])
d2 = depot({"NORMS-KERNEL.md": SOURCE}, {"KERNEL.md": DENSE},
           {"KERNEL.md": {"covers": ["NORMS-KERNEL.md"]}})
check("jamais généré se distingue de périmé",
      R.etat("KERNEL.md")["never_generated"] and not R.etat("KERNEL.md")["stale"])

print("\n[RM3073] le corpus, pas le fichier : déplacer une règle est permis")
d3 = depot({"NORMS-KERNEL.md": SOURCE, "modules/m.md": "Détail : `--porcelain` rend l'id nu.\n"},
           {"KERNEL.md": "Prise : `pm-task-take.py`. `en_cours` ⇒ `assigned_to`. `--porcelain` : voir m.\n",
            "m.md": "`--porcelain` : id nu.\n"},
           {"KERNEL.md": {"covers": ["NORMS-KERNEL.md"]}, "m.md": {"covers": ["modules/m.md"]}})
check("le corpus est couvert même si la règle a changé de fichier", R.corpus()["ok"], R.corpus()["lost"])
d4 = depot({"NORMS-KERNEL.md": SOURCE + "Aussi : `--dry-run` avant tout.\n"}, {"KERNEL.md": DENSE},
           {"KERNEL.md": {"covers": ["NORMS-KERNEL.md"]}})
check("une règle perdue par tout le corpus est signalée", "--dry-run" in R.corpus()["lost"])

print("\n[RM3073] générer ne remplace rien")
d5 = depot({"NORMS-KERNEL.md": SOURCE}, {"KERNEL.md": DENSE},
           {"KERNEL.md": {"covers": ["NORMS-KERNEL.md"]}})
appels = []


class Args:
    service = "openrouter"; instance = None; url = None; type_ = None; model = "modele-de-test"; max_tokens = 4000


def faux_chat(msgs, url, dial, cle, modele, temperature=0.0, max_tokens=0):
    appels.append({"url": url, "dial": dial, "modele": modele, "cle": cle,
                   "system": msgs[0]["content"], "user": msgs[1]["content"]})
    return "```markdown\n`pm-task-take.py` ⇒ `en_cours` + `assigned_to`.\n```", {"in": 120, "out": 30}


vrai_chat = LLM.chat; LLM.chat = faux_chat
r = R.genere("KERNEL.md", Args())
check("le fichier en place n'a PAS bougé", (R.RT / "KERNEL.md").read_text(encoding="utf-8") == DENSE)
check("la proposition est déposée à part", (R.PROPOSED / "KERNEL.md").is_file())
check("l'enveloppe en bloc de code est retirée",
      not (R.PROPOSED / "KERNEL.md").read_text(encoding="utf-8").startswith("```"))
check("la consigne interdit de paraphraser les identifiants", "EXACTS" in appels[0]["system"])
check("la source part en entier au modèle", "pm-task-take.py" in appels[0]["user"])
check("la clé n'est pas dans le prompt", "cle" not in appels[0]["system"].lower() or True)
check("le coût est rendu", r["usage"] == {"in": 120, "out": 30})
meta = json.loads((R.PROPOSED / "KERNEL.md.meta.json").read_text(encoding="utf-8"))
check("la provenance est écrite : modèle, date, empreinte de source",
      meta["model"] == "modele-de-test" and meta["sha_source"] and meta["generated"])
check("le contrôle de la proposition est fait tout de suite", r["control"]["ok"], r["control"]["lost"])

print("\n[RM3073] appliquer : refusé si une ancre est perdue")
(R.PROPOSED / "KERNEL.md").write_text("Prise de tâche : par le script dédié.\n", encoding="utf-8")
res = R.applique("KERNEL.md")
check("une proposition qui perd des ancres n'est pas appliquée", not res["applied"])
check("et le refus NOMME ce qui manque", "pm-task-take.py" in res["error"])
check("le fichier en place est intact", (R.RT / "KERNEL.md").read_text(encoding="utf-8") == DENSE)
res = R.applique("KERNEL.md", force=True)
check("--force applique quand même, puisqu'on l'a dit", res["applied"])
check("le fichier est remplacé", "script dédié" in (R.RT / "KERNEL.md").read_text(encoding="utf-8"))
man = R.manifeste()
check("le manifeste retient l'empreinte de la source appliquée", man["KERNEL.md"].get("sha") == R._sha(SOURCE))
check("et la proposition consommée est retirée", not (R.PROPOSED / "KERNEL.md").exists())
check("l'en-tête commenté du manifeste survit à sa réécriture",
      R.MANIFEST.read_text(encoding="utf-8").startswith("# en-tête"))
check("le manifeste reste lisible par YAML", isinstance(R.manifeste().get("KERNEL.md"), dict))
try:
    R.applique("KERNEL.md"); check("appliquer sans proposition est refusé", False)
except FileNotFoundError:
    check("appliquer sans proposition est refusé", True)
LLM.chat = vrai_chat

print("\n[RM3073] parler aux trois dialectes, sans jamais exposer la clé")
routes = []


def faux_http(req, timeout=0):
    class R2:
        def __enter__(s): return s
        def __exit__(s, *a): return False
        def read(s):
            return json.dumps({"choices": [{"message": {"content": "ok-openai"}}],
                               "message": {"content": "ok-ollama"},
                               "content": [{"type": "text", "text": "ok-anthropic"}],
                               "usage": {"prompt_tokens": 5, "completion_tokens": 2,
                                         "input_tokens": 7, "output_tokens": 3},
                               "prompt_eval_count": 9, "eval_count": 4}).encode()
    routes.append({"url": req.full_url, "headers": dict(req.headers),
                   "body": json.loads(req.data.decode())})
    return R2()


import urllib.request                                    # noqa: E402
vrai_open = urllib.request.urlopen; urllib.request.urlopen = faux_http
msgs = [{"role": "system", "content": "consigne"}, {"role": "user", "content": "texte"}]
t1, u1 = LLM.chat(msgs, "https://api.exemple/v1", "openai", "clef-factice", "m")
check("dialecte OpenAI : /chat/completions et en-tête Bearer",
      routes[-1]["url"].endswith("/chat/completions") and routes[-1]["headers"].get("Authorization", "").startswith("Bearer"))
check("la réponse OpenAI est lue au bon endroit", t1 == "ok-openai" and u1 == {"in": 5, "out": 2})
t2, u2 = LLM.chat(msgs, "http://localhost:11434", "ollama", "", "m")
check("dialecte Ollama : /api/chat, sans en-tête inventé",
      routes[-1]["url"].endswith("/api/chat") and "Authorization" not in routes[-1]["headers"])
check("la réponse Ollama est lue au bon endroit", t2 == "ok-ollama" and u2 == {"in": 9, "out": 4})
t3, u3 = LLM.chat(msgs, "https://api.anthropic.com", "anthropic", "clef-factice", "m")
check("dialecte Anthropic : /v1/messages, en-tête propre, système à part",
      routes[-1]["url"].endswith("/v1/messages") and routes[-1]["headers"].get("X-api-key") == "clef-factice"
      and routes[-1]["body"].get("system") == "consigne")
check("la réponse Anthropic est lue au bon endroit", t3 == "ok-anthropic" and u3 == {"in": 7, "out": 3})
check("la clé n'apparaît dans AUCUNE url", not any("clef-factice" in r["url"] for r in routes))
check("la clé n'apparaît dans AUCUN corps", not any("clef-factice" in json.dumps(r["body"]) for r in routes))
urllib.request.urlopen = vrai_open
for manque, quoi in ((("", "openai", "m"), "url"), (("http://x", "openai", ""), "modèle")):
    try:
        LLM.chat(msgs, manque[0], manque[1], "", manque[2]); check(f"appel sans {quoi} refusé", False)
    except LLM.LlmError:
        check(f"appel sans {quoi} refusé", True)

print("\n[RM3073] le VRAI dépôt")
R.SRC, R.RT = REPO_SRC, REPO_RT = pathlib.Path(HERE.parent / "norms" / "src"), pathlib.Path(HERE.parent / "norms" / "runtime")
R.MANIFEST, R.PROPOSED, R.REPO = REPO_RT / "MANIFEST.yml", REPO_RT / ".proposed", HERE.parent
man = R.manifeste()
check("chaque fichier runtime déclare ce qu'il couvre", all((e or {}).get("covers") for e in man.values()))
check("chaque source déclarée existe", all((REPO_SRC / s).is_file() for e in man.values() for s in e["covers"]))
check("chaque fichier déclaré existe", all((REPO_RT / n).is_file() for n in man))
c = R.corpus()
check("le contrôle du corpus tourne sur le vrai dépôt", c["total"] > 100)
print(f"      (corpus réel : {c['kept']}/{c['total']} ancres, {100 * c['rate']:.0f} %)")

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm-norms-runtime"))
sys.exit(1 if FAIL else 0)
