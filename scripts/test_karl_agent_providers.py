#!/usr/bin/env python3
"""Tests RM3068 — fournisseurs côté serveur : catalogue, déclaration dans la surcharge locale (jamais
dans le fichier commenté), état des clés sans jamais rendre leur valeur, affectation par projet et rôle."""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core            # noqa: E402
hermetic_core()   # RM3076 : core jetable AVANT tout import de module PM (le `.env` du dépôt
                  # n'existe pas dans un worktree de dev — sans ça le test est vert ici, rouge là-bas)
tmp = tempfile.mkdtemp(prefix="karl-prov-"); base = pathlib.Path(tmp) / "clients"
os.environ["KARL_AGENT_PROJECTS_BASE"] = str(base); os.environ["KARL_JOURNAL_DIR"] = tmp; os.environ["KARL_JOURNAL_STDERR"] = "0"
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec); sys.modules["karl_agent"] = ka; spec.loader.exec_module(ka)
import pm_provider_types as PT                      # noqa: E402
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


print("[RM3068] catalogue")
cat = ka.op_provider_types()
check("les cinq axes, dans l'ordre", [a["axis"] for a in cat["axes"]] == ["task", "forge", "doc", "secret", "llm"])
check("redmine, gogs, gitlab, github et les moteurs y sont", {"redmine", "gogs", "gitlab", "github", "ollama", "lemonade"} <= {t["type"] for t in cat["types"]})
ol = next(t for t in cat["types"] if t["type"] == "ollama")
check("ollama : url + modèle, et une clé nommée (pas de valeur)", {f["name"] for f in ol["fields"]} == {"url", "model"} and ol["secrets"][0]["key"] == "API_KEY")
check("aucune valeur de secret dans le catalogue", not any("value" in s for t in cat["types"] for s in t["secrets"]))

print("\n[RM3068] déclaration : la surcharge locale, jamais le fichier commenté")
ka.REPO_ROOT = pathlib.Path(tmp) / "core"; (ka.REPO_ROOT / "scripts").mkdir(parents=True)
(ka.REPO_ROOT / "scripts" / "pm-provider-secret.py").symlink_to(HERE / "pm-provider-secret.py")
commente = ka.REPO_ROOT / "pm.config.yml"
commente.write_text("# un commentaire précieux\nproviders:\n  defaults: {task: redmine-ipro}\n  servers:\n    redmine-ipro: {axis: task, type: redmine, url: 'https://r.example'}\n")
r = ka.op_provider_save({"name": "ollama-strix", "type": "ollama", "fields": {"url": "http://strix.lan:11434", "model": "qwen3:8b"}})
check("instance déclarée avec son axe déduit du type", r["axis"] == "llm" and r["type"] == "ollama")
check("le fichier commenté n'a pas bougé", "# un commentaire précieux" in commente.read_text() and "ollama-strix" not in commente.read_text())
loc = (ka.REPO_ROOT / "pm.config.local.yml").read_text()
check("écrit dans la surcharge locale, avec son en-tête", "ollama-strix" in loc and "ÉCRIT PAR LE COCKPIT" in loc)
check("aucun secret dans la surcharge", "API_KEY" not in loc and "token" not in loc.lower())
try:
    ka.op_provider_save({"name": "x", "type": "zzz", "fields": {}}); check("type inconnu refusé", False)
except ka.ApiError:
    check("type inconnu refusé", True)
try:
    ka.op_provider_save({"name": "../evasion", "type": "ollama", "fields": {"url": "u"}}); check("nom d'instance dangereux refusé", False)
except ka.ApiError:
    check("nom d'instance dangereux refusé", True)
try:
    ka.op_provider_save({"name": "sans-url", "type": "gitlab", "fields": {}}); check("champ requis manquant refusé", False)
except ka.ApiError as e:
    check("champ requis manquant refusé", "url" in str(getattr(e, "msg", e)))
r = ka.op_provider_save({"name": "gogs-cli", "type": "gogs", "fields": {"url": "https://g.example", "ssh_aliases": "a, b"}})
import yaml
srv = yaml.safe_load((ka.REPO_ROOT / "pm.config.local.yml").read_text())["providers"]["servers"]
check("les alias SSH passent d'une saisie « a, b » à une liste", srv["gogs-cli"]["ssh_aliases"] == ["a", "b"])
ka.op_provider_save({"default_for": "llm", "name": "ollama-strix"})
check("défaut d'axe posé", yaml.safe_load((ka.REPO_ROOT / "pm.config.local.yml").read_text())["providers"]["defaults"]["llm"] == "ollama-strix")

print("\n[RM3068] secrets : écriture seule")
# comportement, pas texte : on pose une vraie clé dans un .env isolé, et on regarde ce que l'API en dit
home = pathlib.Path(tmp) / "home"; (home / ".config" / "mmi-pm").mkdir(parents=True)
(home / ".config" / "mmi-pm" / ".env").write_text("SECRET__VW__CLIENTID=valeur-tres-secrete\nSECRET__VW__CLIENTSECRET=\n")
ka.op_provider_save({"name": "vw", "type": "vaultwarden", "fields": {"url": "https://v.example"}})
os.environ["HOME"] = str(home)
vue = ka.op_providers({"user": "zzz-inexistant", "admin": False})     # user inconnu → le compte du démon, HOME isolé
inst = next(i for i in vue["instances"] if i["name"] == "vw")
etats = {s["key"]: s["set"] for s in inst["secrets"]}
check("l'état d'une clé posée et d'une clé vide est rendu", etats == {"CLIENTID": True, "CLIENTSECRET": False}, str(etats))
check("la valeur n'apparaît NULLE PART dans la réponse", "valeur-tres-secrete" not in json.dumps(vue, ensure_ascii=False))
check("le nom de la variable est rendu (pour l'afficher), pas son contenu", inst["secrets"][0]["var"] == "SECRET__VW__CLIENTID")
try:
    ka.op_provider_secret({"name": "vw", "key": "CLIENTID", "type": "vaultwarden", "scope": "global", "value": "x"},
                          {"user": "mathieu", "admin": False}); check("le .env global exige d'être admin", False)
except ka.ApiError as e:
    check("le .env global exige d'être admin", getattr(e, "code", 0) == 403)
try:
    ka.op_provider_secret({"name": "vw", "key": "AUTRE", "type": "vaultwarden", "value": "x"}, {"admin": True})
    check("clé hors catalogue refusée", False)
except ka.ApiError:
    check("clé hors catalogue refusée", True)
try:
    ka.op_provider_secret({"name": "vw", "key": "CLIENTID", "type": "vaultwarden", "value": "   "}, {"admin": True})
    check("valeur vide refusée", False)
except ka.ApiError:
    check("valeur vide refusée", True)

print("\n[RM3068] affectation : le rôle appartient au couple projet ↔ instance")
p = base / "acme" / "projects" / "site"; p.mkdir(parents=True)
(p / "meta.yml").write_text("slug: site\nclient: acme\n")
ka.op_provider_assign({"client": "acme", "project": "site", "axis": "task", "instance": "redmine-matnat",
                       "role": "primary", "params": {"project_id": 12}})
ka.op_provider_assign({"client": "acme", "project": "site", "axis": "task", "instance": "redmine-ipro", "role": "secondary"})
d = yaml.safe_load((p / "meta.yml").read_text())
check("primaire en tête, secondaire ensuite, paramètres conservés",
      [e["instance"] for e in d["providers"]["task"]] == ["redmine-matnat", "redmine-ipro"] and d["providers"]["task"][0]["project_id"] == 12)
q = base / "acme" / "projects" / "autre"; q.mkdir(parents=True); (q / "meta.yml").write_text("slug: autre\n")
ka.op_provider_assign({"client": "acme", "project": "autre", "axis": "task", "instance": "redmine-matnat", "role": "secondary"})
aff = ka._provider_assignments()
roles = {(a["project"], a["instance"]): a["role"] for a in aff}
check("la MÊME instance est primaire ici et secondaire là", roles[("site", "redmine-matnat")] == "primary" and roles[("autre", "redmine-matnat")] == "secondary", str(roles))
ka.op_provider_assign({"client": "acme", "project": "autre", "axis": "task", "instance": "redmine-matnat", "delete": True})
check("retrait d'une affectation", not any(a["project"] == "autre" for a in ka._provider_assignments()))
check("le meta.yml du projet reste valide", "slug" in yaml.safe_load((q / "meta.yml").read_text()))

print("\n" + ("ÉCHEC : " + ", ".join(fails) if fails else "OK — fournisseurs (RM3068)"))
sys.exit(1 if fails else 0)
