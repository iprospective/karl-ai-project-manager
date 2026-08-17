#!/usr/bin/env python3
"""Tests RM2702 — contacts clients (nom, prénom, email, téléphone).

Unitaire, sans réseau, sur un `meta.yml` temporaire : schéma des champs, refus des
doublons et des emails invalides, téléphone conservé en chaîne, marquage `internal`
de nos propres adresses, fiches vides du gabarit ignorées, écriture préservant
l'ordre des clés et le reste du fichier.

Lancer : python3 scripts/test_pm_client_contact.py
"""
import argparse
import importlib.util
import pathlib
import sys
import tempfile

import yaml

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pcc", HERE / "pm-client-contact.py")
P = importlib.util.module_from_spec(spec)
sys.modules["pcc"] = P
spec.loader.exec_module(P)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2702-"))
META = {
    "schema_version": "1.6.0", "slug": "demo", "name": "Demo", "type": "client",
    "status": "active", "created": "2026-01-01",
    "contacts": [{"name": "Mathieu Moulin", "email": "mathieu@iprospective.fr",
                  "role": "owner"}],
    "defaults": {"priority": "normal"}, "aspects": ["overview"],
}
meta_file = tmp / "meta.yml"
meta_file.write_text(yaml.safe_dump(META, sort_keys=False, allow_unicode=True),
                     encoding="utf-8")


class FakeCfg:
    def path(self, key, entity=None, **kw):
        # entity_client_dir → …/<client>/client ; meta.yml est son parent
        return tmp / "client"

    def iter_entities(self):
        return [("demo", None), ("autre", None)]

    def client_meta(self, slug):
        return yaml.safe_load(meta_file.read_text(encoding="utf-8")) if slug == "demo" else {}

    def iter_projects(self, entity=None):
        return iter([])

    def project_meta(self, e, p):
        return {}


cfg = FakeCfg()
P.meta_path = lambda cfg, client: meta_file          # une seule fiche pour le test


def args(**kw):
    base = dict(client="demo", email=None, last_name=None, first_name=None,
                phone=None, role=None, title=None, dry_run=False, only_real=False,
                apply=False)
    base.update(kw)
    return argparse.Namespace(**base)


def contacts():
    return yaml.safe_load(meta_file.read_text(encoding="utf-8"))["contacts"]


# ── ajout : les quatre champs demandés ───────────────────────────────────────
P.cmd_add(cfg, args(email="claire@demo.fr", last_name="Dupont", first_name="Claire",
                    phone=" +33 6 12  34 56 78 ", role="technique", title="Gérante"))
c = P.find_contact(contacts(), "claire@demo.fr")
check("ajout : nom, prénom, email enregistrés",
      c and (c["last_name"], c["first_name"], c["email"]) == ("Dupont", "Claire", "claire@demo.fr"))
check("ajout : téléphone normalisé et gardé en chaîne",
      isinstance(c.get("phone"), str) and c["phone"] == "+33 6 12 34 56 78")
check("ajout : rôle enregistré", c.get("role") == "technique")
check("ajout : fonction en clair conservée", c.get("title") == "Gérante")
check("ajout : contact externe non marqué interne", "internal" not in c)

# ── garde-fous ───────────────────────────────────────────────────────────────
def refuses(fn, a):
    try:
        fn(cfg, a)
        return False
    except SystemExit:
        return True


check("doublon d'email refusé",
      refuses(P.cmd_add, args(email="claire@demo.fr", last_name="Autre")))
check("email invalide refusé", refuses(P.cmd_add, args(email="pas-une-adresse")))
check("contact sans email ni nom refusé", refuses(P.cmd_add, args(phone="0102030405")))
check("client inconnu refusé", refuses(P.cmd_add, args(client="inexistant", email="a@b.fr")))
check("modification d'un inconnu refusée",
      refuses(P.cmd_set, args(email="personne@demo.fr", phone="0102030405")))
check("modification sans champ refusée", refuses(P.cmd_set, args(email="claire@demo.fr")))

# ── nos adresses : marquées, donc non routables ──────────────────────────────
P.cmd_add(cfg, args(email="karl@iprospective.fr", first_name="Karl"))
check("nos adresses marquées internal à l'ajout",
      P.find_contact(contacts(), "karl@iprospective.fr").get("internal") is True)
check("adresse maison détectée", P.is_internal("mathieu@iprospective.fr"))
check("adresse client non détectée comme maison", not P.is_internal("claire@demo.fr"))

P.cmd_mark_internal(cfg, args(client="demo", apply=True))
check("marquage rétroactif de l'entrée du gabarit",
      P.find_contact(contacts(), "mathieu@iprospective.fr").get("internal") is True)

# ── reprise d'une fiche ancienne (champ `name` en un bloc) ───────────────────
P.cmd_set(cfg, args(email="mathieu@iprospective.fr", last_name="Moulin",
                    first_name="Mathieu"))
c = P.find_contact(contacts(), "mathieu@iprospective.fr")
check("reprise : nom structuré", (c["last_name"], c["first_name"]) == ("Moulin", "Mathieu"))
check("reprise : ancien champ `name` retiré (plus de doublon)", "name" not in c)

# ── fiches vides du gabarit ──────────────────────────────────────────────────
check("fiche vide reconnue", P.is_empty({"name": "", "email": "", "role": "owner"}))
check("fiche nommée non vide", not P.is_empty({"name": "Lydie Mariller", "email": ""}))
check("fiche avec téléphone seul non vide", not P.is_empty({"phone": "0475000000"}))
check("fiche avec fonction seule non vide", not P.is_empty({"title": "Gérant"}))

# ── modification et retrait ──────────────────────────────────────────────────
P.cmd_set(cfg, args(email="claire@demo.fr", phone="04 75 00 00 00", role="decideur"))
c = P.find_contact(contacts(), "claire@demo.fr")
check("modification : téléphone et rôle mis à jour",
      (c["phone"], c["role"]) == ("04 75 00 00 00", "decideur"))
check("modification : les autres champs intacts", c["last_name"] == "Dupont")

before = len(contacts())
P.cmd_remove(cfg, args(email="claire@demo.fr"))
check("retrait effectif", len(contacts()) == before - 1
      and P.find_contact(contacts(), "claire@demo.fr") is None)

# ── le reste du fichier survit ───────────────────────────────────────────────
final = yaml.safe_load(meta_file.read_text(encoding="utf-8"))
check("meta.yml : autres clés préservées",
      final["slug"] == "demo" and final["aspects"] == ["overview"]
      and final["defaults"]["priority"] == "normal")
check("meta.yml : ordre des clés préservé",
      list(final.keys())[:4] == ["schema_version", "slug", "name", "type"])

# ── dry-run ──────────────────────────────────────────────────────────────────
snapshot = meta_file.read_text(encoding="utf-8")
P.cmd_add(cfg, args(email="test@demo.fr", last_name="Test", dry_run=True))
check("dry-run n'écrit rien", meta_file.read_text(encoding="utf-8") == snapshot)

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
