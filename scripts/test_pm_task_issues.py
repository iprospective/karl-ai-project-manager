#!/usr/bin/env python3
"""Tests RM3113 — les *issues* d'une forge comme gestionnaire de tickets.

Ce qui doit tenir : les trois types sont déclarables depuis les réglages (catalogue), GitHub et Gogs
partagent UN backend (Gogs mime l'API de GitHub), les capacités sont dites honnêtement plutôt que
découvertes à l'usage, une demande de fusion n'est pas un ticket, et l'écriture est refusée avec son
motif tant que la question des champs n'est pas tranchée.

Lancer : python3 scripts/test_pm_task_issues.py
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_provider_types as PT          # noqa: E402
import pm_task                          # noqa: E402
import pm_forge                         # noqa: E402

FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


print("[RM3113] déclarables depuis les réglages")
task_types = {k: v for k, v in PT.CATALOGUE.items() if v["axis"] == "task"}
check("les trois forges rejoignent Redmine sur l'axe « Tickets »",
      set(task_types) == {"redmine", "gitlab_issues", "github_issues", "gogs_issues"},
      str(sorted(task_types)))
for t in ("gitlab_issues", "github_issues", "gogs_issues"):
    champs = {f[0] for f in task_types[t]["fields"]}
    check(f"{t} demande le dépôt qui porte les tickets", "repo" in champs, str(sorted(champs)))
    check(f"{t} attend un jeton, pas un mot de passe",
          [n for n, _ in task_types[t]["secrets"]] == ["TOKEN"])
    check(f"{t} prévient de ce qu'il ne sait pas faire", bool(task_types[t].get("note")))
check("github_issues sait viser une instance Enterprise",
      "api_url" in {f[0] for f in task_types["github_issues"]["fields"]})

print("\n[RM3113] un backend par type, un transport partagé")
check("les quatre backends sont enregistrés",
      set(pm_task._BACKENDS) == {"redmine", "gitlab_issues", "github_issues", "gogs_issues"})
check("GitHub et Gogs partagent le MÊME backend — Gogs mime l'API de GitHub",
      issubclass(pm_task.GithubIssuesTaskProvider, pm_task._GithubStyleIssuesTaskProvider)
      and issubclass(pm_task.GogsIssuesTaskProvider, pm_task._GithubStyleIssuesTaskProvider))
check("chacun apporte sa forge de transport",
      pm_task.GithubIssuesTaskProvider(repo="a/b").forge_class is pm_forge.GithubForge
      and pm_task.GogsIssuesTaskProvider(repo="a/b").forge_class is pm_forge.GogsForge)
try:
    pm_task.GithubIssuesTaskProvider()
    check("sans dépôt, le backend refuse de se construire", False, "aucune erreur")
except pm_task.TaskProviderError as e:
    check("sans dépôt, le backend refuse de se construire", "repo" in str(e))

print("\n[RM3113] les capacités sont dites, pas découvertes")
for cls in (pm_task.GithubIssuesTaskProvider, pm_task.GogsIssuesTaskProvider):
    c = cls.capabilities
    check(f"{cls.name} : ni champs perso, ni temps, ni tag IA",
          not c.custom_fields and not c.time_tracking and not c.ia_tag)
    check(f"{cls.name} : pas de recherche serveur annoncée (on filtre en local)",
          not c.full_text_search)

print("\n[RM3113] lecture : une demande de fusion n'est pas un ticket")


class FausseForge:
    """Forge de transport en mémoire — aucune requête ne part."""
    def __init__(self, repo_path, instance=None):
        self.repo_path = repo_path
        self.vu = []

    def token(self, role):
        return "jeton"

    def api(self, method, path, token, fields=None):
        self.vu.append((method, path))
        if "/issues/7" in path:
            return 200, {"number": 7, "title": "Un ticket", "body": "corps"}, ""
        if path.startswith("/repos/acme/site/issues"):
            return 200, [{"number": 1, "title": "vrai ticket", "body": "du texte"},
                         {"number": 2, "title": "une fusion", "pull_request": {"url": "…"}},
                         {"number": 3, "title": "autre", "body": "mot-clé dedans"}], ""
        if path == "/repos/acme/site":
            return 200, {"full_name": "acme/site"}, ""
        return 404, None, "absent"


class Faux(pm_task._GithubStyleIssuesTaskProvider):
    name = "faux_issues"
    forge_class = FausseForge


p = Faux(repo="acme/site")
check("un ticket se lit par son numéro DANS LE DÉPÔT", p.fetch_issue(7)["number"] == 7)
liste = p.list_issues()
check("la liste écarte les demandes de fusion", [i["number"] for i in liste] == [1, 3], str(liste))
check("la fiche du dépôt se lit", p.fetch_project(None)["full_name"] == "acme/site")
check("la recherche cherche dans le titre ET le corps",
      [i["number"] for i in p.search_issues("mot-clé")] == [3])
check("…et une recherche vide ne rend rien plutôt que tout", p.search_issues("  ") == [])

print("\n[RM3113] écriture : refusée avec son motif, pas en silence")
for geste, args in (("add_note", (1, "note")), ("create_issue", ()), ("set_parent", (1, 2))):
    try:
        getattr(p, geste)(*args)
        check(f"{geste} refusé", False, "aucune erreur")
    except pm_task.TaskProviderError as e:
        check(f"{geste} refusé, et il dit pourquoi", len(str(e)) > 20, str(e))

print("\n[RM3113] un backend inconnu est nommé avec ceux qui existent")
try:
    pm_task._backend_for(type("I", (), {"type": "jira"})())
    check("backend inconnu refusé", False)
except pm_task.TaskProviderError as e:
    check("backend inconnu refusé, et les connus sont listés",
          "jira" in str(e) and "gogs_issues" in str(e) and "redmine" in str(e))

print("\n[RM3113] Gogs a bien une API — seulement pas pour les PR")
g = pm_forge.GogsForge("acme/site")
check("la forge Gogs sait parler à l'API v1", callable(getattr(g, "api", None)))
st, data, raw = g.api("GET", "/repos/acme/site", "")
check("sans URL d'instance, elle le DIT au lieu d'échouer obscurément",
      st == 0 and "Gogs" in str(raw), f"{st} {raw}")

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — issues comme gestionnaire de tickets (RM3113)"))
sys.exit(1 if FAIL else 0)
