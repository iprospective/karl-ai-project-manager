"""pm_tags — étiquettes de ticket (RM2829, chantier RM2828).

Le vocabulaire transverse d'un ticket (`front`, `bo`, `bdd`, `refacto`,
`livraison`, `tunnel-de-commande`…) vit à DEUX endroits qui doivent dire la même
chose (principe de parité, NORMS `redmine-sync`) :

  - `tags: []` au frontmatter — déjà écrit par `pm-task-add --tags`, déjà filtré
    par `pm-task-list --tag` ;
  - un **custom field Redmine « liste » à valeurs multiples**, partagé à tous les
    projets — sans quoi l'étiquette est invisible dans l'UI et dans les vues.

Pourquoi un CF et pas autre chose (constat vérifié sur l'instance, 2026-08-25) :
Redmine n'a pas de tags en standard et aucun plugin n'est installé ; les
CATÉGORIES de ticket existent mais sont mono-valeur et propres à chaque projet —
« refacto » serait à recréer partout, et un ticket ne pourrait pas être « front »
ET « refacto ».

⚠ Le CF se crée à la main (l'API Redmine ne crée pas de custom fields — lecture
seule). Tant qu'il n'existe pas, TOUT ici fonctionne côté frontmatter et le push
Redmine se dégrade avec un message : la parité est un objectif, pas un blocage.
Marche à suivre : `knowledge/redmine/etiquettes.md`.

⚠⚠ Le CF livré est en format **enumeration** (et non « liste ») : l'API attend
l'**id** de chaque valeur (45, 46…), jamais son libellé — un push de labels est
refusé. La table slug ↔ label ↔ id vit dans `tags.registry.yml`, qui doit rester
synchrone avec la définition Redmine. Une étiquette hors registre ne peut pas
être poussée : le dire ici vaut mieux qu'un 422 opaque au moment du PUT.
"""
import os
import re
import sys
import unicodedata

CF_NAME = "Tags"                # nom du CF côté Redmine (id 32, créé le 2026-08-26)
REGISTRY = "tags.registry.yml"  # valeurs possibles : slug ↔ label ↔ id (RM2829)
ENV_VAR = "REDMINE_CF_TAGS_ID"  # override explicite, comme les autres CF
MAX_TAGS = 12                   # un ticket étiqueté douze fois n'est plus étiqueté
MAX_LEN = 40


def normalize(tag):
    """Une étiquette est un slug : minuscules, sans accent, tirets.

    « Tunnel de Commande », « tunnel_de_commande » et « TUNNEL DE COMMANDE »
    doivent être LA MÊME étiquette — sinon le filtre par étiquette rend trois
    listes disjointes, et l'utilisateur conclut que le filtre ne marche pas.
    """
    s = unicodedata.normalize("NFKD", str(tag or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:MAX_LEN].rstrip("-")


def clean(tags):
    """Liste d'étiquettes normalisée, dédoublonnée, triée, plafonnée.

    Le tri est délibéré : deux tickets portant les mêmes étiquettes doivent avoir
    le MÊME frontmatter, sinon chaque écriture produit un diff qui ne dit rien.
    """
    out = []
    for t in tags or []:
        n = normalize(t)
        if n and n not in out:
            out.append(n)
    return sorted(out)[:MAX_TAGS]


def parse_csv(raw):
    """« front, bo ; refacto » → ['bo', 'front', 'refacto'] (virgule ou point-virgule)."""
    return clean(re.split(r"[;,]", str(raw or "")))


def apply_change(current, add=None, remove=None, replace=None):
    """Nouvelle liste d'étiquettes après un geste. Pure, sans I/O.

    `replace` prime sur add/remove : « mets exactement ça » est une intention
    différente de « ajoute/retire », et les mélanger silencieusement produirait
    un résultat que personne n'a demandé.
    """
    if replace is not None:
        return clean(replace)
    out = clean(current)
    for t in clean(add):
        if t not in out:
            out.append(t)
    drop = set(clean(remove))
    return sorted([t for t in out if t not in drop])[:MAX_TAGS]


def _registry_path():
    """Chemin du registre.

    Le registre voyage AVEC le code (il est versionné à la racine du dépôt, comme
    `redmine.reference.yml` — même résolution, volontairement) : le code qui
    s'exécute doit lire SON registre, sinon un worktree de développement pousserait
    des ids venus d'un autre checkout. `PM_CORE_DIR` reste un repli explicite.
    """
    import os
    from pathlib import Path
    ici = Path(__file__).resolve().parent.parent / REGISTRY
    if ici.is_file():
        return ici
    core = os.environ.get("PM_CORE_DIR")
    return (Path(core).expanduser() / REGISTRY) if core else ici


def load_registry():
    """{slug: {label, id}} — les valeurs possibles du CF. Vide si le registre est
    absent ou illisible : on dégrade vers le frontmatter seul plutôt que d'échouer."""
    try:
        import yaml
        data = yaml.safe_load(_registry_path().read_text(encoding="utf-8")) or {}
    except Exception:       # noqa: BLE001 — registre absent/cassé : miroir local
        return {}
    out = {}
    for v in data.get("values") or []:
        if not isinstance(v, dict):
            continue
        slug = normalize(v.get("slug") or v.get("label"))
        if slug and v.get("id") is not None:
            out[slug] = {"label": str(v.get("label") or slug), "id": str(v["id"])}
    return out


def load_aliases():
    """{alias: valeur canonique} — le mapping n-1 (RM2836), aplati et normalisé.

    Un alias qui serait AUSSI une valeur canonique est ignoré : il se router ait
    lui-même, et l'erreur passerait inaperçue.
    """
    try:
        import yaml
        data = yaml.safe_load(_registry_path().read_text(encoding="utf-8")) or {}
    except Exception:       # noqa: BLE001
        return {}
    vals = {normalize(v.get("slug") or v.get("label"))
            for v in (data.get("values") or []) if isinstance(v, dict)}
    out = {}
    for canon, liste in (data.get("aliases") or {}).items():
        c = normalize(canon)
        if c not in vals:
            continue
        for a in liste or []:
            k = normalize(a)
            if k and k not in vals:
                out[k] = c
    return out


def canonical(tag):
    """(valeur retenue, alias d'origine) — `ui` → (`front`, `ui`).

    Rendre l'origine permet de le DIRE : une étiquette silencieusement réécrite
    donne l'impression que le geste a été ignoré.
    """
    t = normalize(tag)
    if not t:
        return "", None
    a = load_aliases()
    return (a[t], t) if t in a else (t, None)


def pending_values():
    """Valeurs déclarées au registre mais pas encore créées côté Redmine (sans id).

    Acceptées à l'écriture locale — le vocabulaire est décidé —, mais impossibles
    à pousser : l'outillage le dit au lieu d'échouer sur un 422.
    """
    try:
        import yaml
        data = yaml.safe_load(_registry_path().read_text(encoding="utf-8")) or {}
    except Exception:       # noqa: BLE001
        return []
    return sorted(normalize(v.get("slug") or v.get("label"))
                  for v in (data.get("values") or [])
                  if isinstance(v, dict) and v.get("id") is None
                  and normalize(v.get("slug") or v.get("label")))


def vocabulary():
    """Tous les slugs du vocabulaire décidé — actifs ET en attente."""
    try:
        import yaml
        data = yaml.safe_load(_registry_path().read_text(encoding="utf-8")) or {}
    except Exception:       # noqa: BLE001
        return []
    return sorted({normalize(v.get("slug") or v.get("label"))
                   for v in (data.get("values") or []) if isinstance(v, dict)
                   and normalize(v.get("slug") or v.get("label"))})


def known_values():
    """Slugs acceptés par le CF (vocabulaire contrôlé). Vide = registre absent."""
    return sorted(load_registry())


def split_known(tags):
    """(connues, inconnues) — une étiquette hors registre ne peut pas être poussée.

    Registre absent : on ne prétend pas savoir, tout est « connu » et le push
    échouera franchement s'il doit échouer.
    """
    reg = load_registry()
    tt = clean(tags)
    if not reg:
        return tt, []
    return [t for t in tt if t in reg], [t for t in tt if t not in reg]


def cf_id():
    """Id du CF « Tags » : override `.env`, sinon le registre, sinon la référence.

    Le registre passe avant `redmine.reference.yml` parce qu'il porte DÉJÀ l'id
    (il en a besoin pour les valeurs) : une seule source à tenir à jour plutôt que
    deux qui peuvent diverger.

    None = CF non configuré (pas encore créé) → miroir frontmatter seul.
    """
    v = (os.environ.get(ENV_VAR) or "").strip()
    if v.isdigit():
        return int(v)
    try:
        import yaml
        data = yaml.safe_load(_registry_path().read_text(encoding="utf-8")) or {}
        rid = ((data.get("cf") or {}).get("id"))
        if isinstance(rid, int) or (isinstance(rid, str) and rid.isdigit()):
            return int(rid)
    except Exception:       # noqa: BLE001 — registre absent : on continue
        pass
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import redmine_utils
        return redmine_utils.cf_id_by_name(CF_NAME)
    except Exception:       # noqa: BLE001 — référence absente : miroir seul
        return None


def cf_payload(tags):
    """Le CF tel que l'API l'attend : une LISTE d'**ids de valeurs** (enumeration).

    Envoyer les libellés serait refusé (422) : le format `enumeration` désigne ses
    valeurs par id. Les étiquettes hors registre sont écartées — les pousser
    ferait échouer TOUT le PUT, y compris les étiquettes valides.

    Redmine veut `value: []` pour vider un CF multi-valeurs — pas `""`, refusé sur
    ce format : le cas « plus aucune étiquette » doit rester exprimable, sinon on
    ne peut jamais retirer la dernière.
    """
    cid = cf_id()
    if cid is None:
        return None
    reg = load_registry()
    if not reg:
        # Pas de registre : on envoie les slugs. C'est le comportement d'un CF
        # « liste » ; sur un CF enumeration, Redmine refusera — franchement.
        return {"id": cid, "value": clean(tags)}
    return {"id": cid, "value": [reg[t]["id"] for t in clean(tags) if t in reg]}


def from_issue(issue):
    """Étiquettes portées par une issue Redmine (dict de l'API) → liste propre.

    La valeur d'un CF multiple arrive en liste ; un CF simple (ou une instance où
    « valeurs multiples » n'a pas été coché) renvoie une chaîne — on accepte les
    deux plutôt que de perdre l'information sur une case décochée.
    """
    cid = cf_id()
    for c in (issue or {}).get("custom_fields") or []:
        if cid is not None and c.get("id") != cid:
            continue
        if cid is None and c.get("name") != CF_NAME:
            continue
        v = c.get("value")
        vals = v if isinstance(v, list) else re.split(r"[;,]", str(v or ""))
        # Une valeur d'enumeration revient en ID (« 45 ») ; un CF « liste »
        # renverrait le libellé. On accepte les deux plutôt que de perdre
        # l'information sur un changement de format côté Redmine.
        par_id = {spec["id"]: slug for slug, spec in load_registry().items()}
        out = []
        for x in vals:
            k = str(x).strip()
            out.append(par_id.get(k, k))
        return clean(out)
    return []
