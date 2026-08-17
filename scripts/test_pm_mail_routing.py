#!/usr/bin/env python3
"""Tests RM2669 — routage expéditeur → client/projet.

Unitaire, sans réseau ni arbo PM réelle (config simulée) : ordre de la cascade,
pièges connus (l'adresse maison présente dans les contacts de TOUS les clients,
l'apprentissage d'un domaine grand public), refus de choisir entre plusieurs
candidats, et apprentissage relu.

Lancer : python3 scripts/test_pm_mail_routing.py
"""
import importlib.util
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_mail_routing", HERE / "pm_mail_routing.py")
R = importlib.util.module_from_spec(spec)
sys.modules["pm_mail_routing"] = R
spec.loader.exec_module(R)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


class FakeCfg:
    """Arbo PM simulée : 2 clients, l'un mono-projet, l'autre multi-projets."""

    def __init__(self, tmp):
        self.conf_dir = pathlib.Path(tmp)
        self.projects_root = pathlib.Path(tmp) / "projects"
        self.tasks = {2661: ("calyclay", "infra")}
        self.projects = {"calyclay": ["dolibarr", "infra"], "abatik": ["site"]}
        self.contacts = {
            # piège réel : le gabarit de création met l'adresse du propriétaire
            # chez TOUS les clients (constaté sur les 20 clients, RM2669)
            "calyclay": ["mathieu@iprospective.fr"],
            "abatik": ["mathieu@iprospective.fr", "contact@abatik.fr"],
        }

    def path(self, key, **kw):
        raise KeyError(key)          # pattern absent → repli conf_dir du module

    def iter_entities(self):
        return [(c, None) for c in self.projects]

    def iter_projects(self, entity=None):
        for c, ps in self.projects.items():
            if entity and c != entity:
                continue
            for p in ps:
                yield c, p, None

    def client_meta(self, slug):
        return {"name": slug.capitalize(),
                "contacts": [{"email": m} for m in self.contacts.get(slug, [])]}

    def find_task(self, rm_id):
        pair = self.tasks.get(int(rm_id))
        if not pair:
            return None
        # …/clients/<client>/projects/<projet>/tasks/RM<id>_x.md
        return (self.projects_root / "clients" / pair[0] / "projects" / pair[1]
                / "tasks" / f"RM{rm_id}_x.md")


tmp = tempfile.mkdtemp(prefix="rm2669-")
cfg = FakeCfg(tmp)


def entry(**kw):
    base = {"from": "contact@exemple.fr", "from_name": "", "rm_id": None, "subject": ""}
    base.update(kw)
    return base


# ── 1. le fil désigne son ticket : il prime sur tout ─────────────────────────
r = R.route(entry(rm_id=2661, **{"from": "info.calyclay@gmail.com"}), cfg)
check("ticket : client ET projet du ticket", (r["client"], r["project"]) == ("calyclay", "infra"))
check("ticket : confiance maximale", r["confidence"] == 1.0 and r["source"] == "ticket")

# ── 2. table apprise ─────────────────────────────────────────────────────────
R.learn(cfg, "info.calyclay@gmail.com", "calyclay/dolibarr")
r = R.route(entry(**{"from": "info.calyclay@gmail.com"}), cfg)
check("mapping : adresse apprise appliquée",
      (r["client"], r["project"], r["source"]) == ("calyclay", "dolibarr", "mapping"))
check("mapping : correction relue à 100 %", r["confidence"] == 1.0)
r = R.route(entry(rm_id=2661, **{"from": "info.calyclay@gmail.com"}), cfg)
check("le fil prime sur la table apprise", r["source"] == "ticket" and r["project"] == "infra")

R.learn(cfg, "qui@abatik.fr", "abatik", domain=True)
r = R.route(entry(**{"from": "autre@abatik.fr"}), cfg)
check("mapping : domaine appris → client",
      (r["client"], r["source"]) == ("abatik", "mapping"))
check("mapping : projet déduit car client mono-projet", r["project"] == "site")

# ── 3. gardes d'apprentissage ────────────────────────────────────────────────
def refuses(addr, target, domain=True):
    try:
        R.learn(cfg, addr, target, domain=domain)
        return False
    except ValueError:
        return True


check("refus d'apprendre gmail.com comme domaine client",
      refuses("info.calyclay@gmail.com", "calyclay"))
check("refus d'apprendre le domaine maison",
      refuses("mathieu@iprospective.fr", "calyclay"))
# adresse (et pas domaine) : autorisée même chez un fournisseur grand public.
# Sur une AUTRE adresse : celle de la file sert aux assertions de relecture.
check("l'adresse gmail reste apprenable",
      not refuses("autre.calyclay@gmail.com", "calyclay", domain=False))
check("cible vide refusée", refuses("x@y.fr", "", domain=False))

# ── 4. compte Redmine de l'expéditeur ────────────────────────────────────────
r = R.route(entry(**{"from": "noe@calyclay.com"}), cfg,
            redmine_lookup=lambda a: [("calyclay", "dolibarr")])
check("redmine : projet unique retenu",
      (r["client"], r["project"], r["source"]) == ("calyclay", "dolibarr", "redmine"))
r = R.route(entry(**{"from": "noe@calyclay.com"}), cfg,
            redmine_lookup=lambda a: [("calyclay", "dolibarr"), ("calyclay", "infra")])
check("redmine : plusieurs projets → projet NON choisi", r["project"] is None)
check("redmine : candidats listés", len(r["candidates"]) == 2 and r["confidence"] < 0.9)
r = R.route(entry(**{"from": "x@z.fr"}), cfg,
            redmine_lookup=lambda a: [("calyclay", "infra"), ("abatik", "site")])
check("redmine : plusieurs clients → rien de choisi",
      r["client"] is None and r["confidence"] == 0.0)
r = R.route(entry(**{"from": "mathieu@iprospective.fr"}), cfg,
            redmine_lookup=lambda a: [("calyclay", "infra")])
check("redmine : adresse maison jamais interrogée", r["source"] != "redmine")

# ── 5. contacts[] — le piège de l'adresse maison ─────────────────────────────
r = R.route(entry(**{"from": "mathieu@iprospective.fr"}), cfg)
check("contacts : adresse maison NE route PAS (présente chez tous les clients)",
      r["client"] is None and r["source"] == "unresolved")
# NB : à ce stade abatik.fr est déjà appris comme domaine (§2) — c'est donc le
# mapping qui répond, et c'est l'ordre voulu. La source `contacts` se teste sur
# un client dont le domaine n'a pas été appris.
r = R.route(entry(**{"from": "contact@abatik.fr"}), cfg)
check("adresse client unique retenue",
      (r["client"], r["project"]) == ("abatik", "site") and r["client"] is not None)
cfg.contacts["calyclay"] = ["mathieu@iprospective.fr", "compta@tiers-payeur.fr"]
r = R.route(entry(**{"from": "compta@tiers-payeur.fr"}), cfg)
check("contacts : source utilisée quand rien d'autre ne répond",
      r["client"] == "calyclay" and r["source"] == "contacts")
check("contacts : projet laissé ouvert si le client en a plusieurs", r["project"] is None)

# ── 6. indice textuel ────────────────────────────────────────────────────────
r = R.route(entry(**{"from": "info.calyclay@free.fr", "from_name": "CalyClay"}), cfg)
check("indice : slug reconnu dans l'expéditeur",
      r["client"] == "calyclay" and r["source"] == "indice")
check("indice : projet laissé ouvert (client multi-projets)", r["project"] is None)
check("indice : confiance intermédiaire", 0 < r["confidence"] < 1)
r = R.route(entry(**{"from": "hello@nulle-part.fr", "from_name": "Inconnu"}), cfg)
check("inconnu : à classer, jamais deviné",
      r["client"] is None and r["source"] == "unresolved" and r["confidence"] == 0.0)
r = R.route(entry(**{"from": "x@y.fr", "from_name": "calyclay et abatik"}), cfg)
check("deux clients reconnus → aucun choisi",
      r["client"] is None and set(r["candidates"]) == {"calyclay", "abatik"})

# ── 7. la table ne contient que du routage ───────────────────────────────────
raw = R.routing_file(cfg).read_text(encoding="utf-8")
check("table versionnable : pas de contenu d'email",
      "addresses:" in raw and "body" not in raw and "subject" not in raw)
check("table : rechargée à l'identique",
      R.load_routing(cfg)["addresses"]["info.calyclay@gmail.com"] == "calyclay/dolibarr")
check("table hors projects_root (dossier non versionné)",
      R.routing_file(cfg).parent == cfg.conf_dir)

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
