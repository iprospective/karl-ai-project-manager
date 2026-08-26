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
"""
import os
import re
import sys
import unicodedata

CF_NAME = "Étiquettes"          # nom du CF côté Redmine (référence : redmine.reference.yml)
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


def cf_id():
    """Id du CF « Étiquettes » : override `.env`, sinon `redmine.reference.yml`.

    None = CF non configuré (pas encore créé) → miroir frontmatter seul.
    """
    v = (os.environ.get(ENV_VAR) or "").strip()
    if v.isdigit():
        return int(v)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import redmine_utils
        return redmine_utils.cf_id_by_name(CF_NAME)
    except Exception:       # noqa: BLE001 — référence absente : miroir seul
        return None


def cf_payload(tags):
    """Le CF tel que l'API l'attend : une LISTE de valeurs (CF multiple).

    Redmine veut `value: []` pour vider un CF multi-valeurs — pas `""`, qui est
    refusé sur ce format. Le cas « plus aucune étiquette » doit donc rester
    exprimable, sinon on ne peut jamais retirer la dernière.
    """
    cid = cf_id()
    if cid is None:
        return None
    return {"id": cid, "value": clean(tags)}


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
        if isinstance(v, list):
            return clean(v)
        return parse_csv(v)
    return []
