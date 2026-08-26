#!/usr/bin/env python3
"""Tests RM2836 — registre des Tags : vocabulaire, alias n-1, garde, audit.

Ce qui est protégé ici :
  1. le mapping n-1 : `ui` s'écrit `front`, et l'origine est RENDUE pour pouvoir
     le dire (une étiquette réécrite en silence passe pour un geste ignoré) ;
  2. la distinction entre une valeur DÉCIDÉE mais pas encore créée côté Redmine
     (poussée impossible, à dire) et un mot-clé purement local ;
  3. la cohérence du registre livré : pas d'alias qui soit aussi une valeur, pas
     d'alias en double, pas de famille sans valeur — trois erreurs qui rendraient
     le routage imprévisible.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_tags

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis")

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


data = yaml.safe_load((HERE.parent / pm_tags.REGISTRY).read_text(encoding="utf-8")) or {}
values = data.get("values") or []
aliases = data.get("aliases") or {}
slugs = {pm_tags.normalize(v.get("slug") or v.get("label")) for v in values}

# — cohérence du registre livré —
check("le registre a des valeurs et des alias", bool(values) and bool(aliases))
check("chaque famille d'alias pointe une valeur existante",
      all(pm_tags.normalize(k) in slugs for k in aliases),
      [k for k in aliases if pm_tags.normalize(k) not in slugs])
plats = [pm_tags.normalize(a) for lst in aliases.values() for a in (lst or [])]
check("aucun alias n'est aussi une valeur (il se router ait lui-même)",
      not (set(plats) & slugs), sorted(set(plats) & slugs))
check("aucun alias en double (à quelle valeur router ?)",
      len(plats) == len(set(plats)),
      [a for a in set(plats) if plats.count(a) > 1])
check("les slugs sont déjà normalisés dans le fichier",
      all(pm_tags.normalize(v.get("slug")) == v.get("slug") for v in values if v.get("slug")))
check("toute valeur a un libellé (c'est lui qui s'affiche dans Redmine)",
      all(str(v.get("label") or "").strip() for v in values))

# — vocabulaire, actives, en attente —
vocab, actives, pend = pm_tags.vocabulary(), pm_tags.known_values(), pm_tags.pending_values()
check("vocabulaire = actives + en attente",
      set(vocab) == set(actives) | set(pend) and not (set(actives) & set(pend)))
check("les valeurs en attente n'ont pas d'id (donc ne peuvent pas être poussées)",
      all(v.get("id") is None for v in values
          if pm_tags.normalize(v.get("slug")) in set(pend)))
if pend:
    p = pm_tags.cf_payload([pend[0]])
    check("une valeur en attente est écartée du payload, sans le faire échouer",
          p is not None and p["value"] == [], p)

# — mapping n-1 —
check("un alias est canonicalisé, avec son origine",
      pm_tags.canonical("ui") == ("front", "ui"), pm_tags.canonical("ui"))
check("la casse et les accents n'y changent rien",
      pm_tags.canonical("UX")[0] == "front" and pm_tags.canonical("Sécurité")[0] == "securite")
check("une valeur canonique n'est pas réécrite",
      pm_tags.canonical("front") == ("front", None))
check("un mot-clé libre reste lui-même (il n'est pas inventé de route)",
      pm_tags.canonical("cockpit") == ("cockpit", None))
check("les produits mono-projet sont VOLONTAIREMENT hors registre",
      all(x not in slugs and x not in plats for x in ("cockpit", "karl", "karl-agent", "norms")))
check("zabbix est mappé (Monitoring) sans être une valeur",
      pm_tags.canonical("zabbix") == ("monitoring", "zabbix"))

# — RM2837 : le registre est remappé sur les valeurs RÉELLES —
check("toutes les valeurs ont un id (le vocabulaire est entièrement créé)",
      all(v.get("id") is not None for v in values),
      [v.get("slug") for v in values if v.get("id") is None])
check("un slug peut différer du libellé (« Debug/Bugfix » s'écrit `debug`)",
      any(pm_tags.normalize(v.get("label")) != v.get("slug") for v in values))
for court, long in (("tooling", "outillage"), ("archi", "architecture"),
                    ("backup", "sauvegarde"), ("debug", "debug-bugfix")):
    check(f"le libellé retenu garde son synonyme en alias : {long} → {court}",
          pm_tags.canonical(long) == (court, long), pm_tags.canonical(long))
check("le paiement rejoint « Tunnel de commande » sans créer de valeur",
      pm_tags.canonical("etransactions")[0] == "tunnel-de-commande")
check("les familles ajoutées à la création sont cartographiées",
      pm_tags.canonical("telegram")[0] == "notifications"
      and pm_tags.canonical("analyses")[0] == "audit")

# — garde à l'écriture : ce que le script doit refuser —
src = (HERE / "pm-task-tag.py").read_text(encoding="utf-8")
check("le refus est explicite et sort en erreur", "hors vocabulaire" in src and "sys.exit(2)" in src)
check("l'échappatoire mot-clé local existe", "--free" in src)
check("les valeurs acceptées sont listées au refus", "valeurs acceptées" in src)

# — audit : les quatre écarts sont bien produits —
audit_src = (HERE / "pm-tags-audit.py").read_text(encoding="utf-8")
for cle in ("a_creer", "a_recopier", "orphelines", "libres"):
    check(f"l'audit produit « {cle} »", f'"{cle}"' in audit_src)
check("l'audit distingue « API injoignable » de « CF vide »",
      "redmine_lu" in audit_src and "None ≠ {}" in audit_src)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests registre des Tags (RM2836) passent")
