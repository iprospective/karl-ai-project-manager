"""pm_roles — quel rôle d'agent pour ce ticket ? (RM2833, chantier RM2828)

Une étiquette dit le DOMAINE d'un ticket (`front`, `bdd`, `infra`…) ; les rôles
d'agent (`agents/worker-*.md`) disent QUI sait le traiter. Faire le lien évite la
question posée à chaque prise : « c'est du dev ou de la base ? ».

Deux principes, tenus par les tests :

- **Le routage PROPOSE, il n'assigne pas.** Une réassignation automatique
  changerait le propriétaire d'un ticket — donc le verrou d'écriture (NORMS :
  « Redmine est le mutex ») — sans que personne l'ait demandé. On rend une
  suggestion et sa raison ; le geste reste humain.
- **La table se déclare en conf, jamais en dur** (`meta.yml`, clé `tag_roles`),
  avec la cascade NORMS client → projet : le projet précise ou surcharge son
  client. Un vocabulaire métier n'a pas à être connu du code.

Exemple (`meta.yml` d'un projet) :

    tag_roles:
      front: dev
      bdd: db
      infra: infra
      design: design
"""
import re

CONF_KEY = "tag_roles"

# Rôles connus = fichiers agents/worker-<rôle>.md. Écrire un rôle inexistant dans
# la conf est une faute qui doit se voir : router vers un fichier absent laisse
# l'agent sans instructions de rôle, et personne ne s'en aperçoit.
KNOWN_ROLES = ("dev", "db", "design", "infra", "analyst")


def _norm(t) -> str:
    """Même slug qu'à l'écriture des étiquettes (cf. pm_tags.normalize)."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(t or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().strip()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def merge_table(client_meta, project_meta) -> dict:
    """Table effective : celle du client, surchargée par celle du projet.

    Cascade NORMS (client → projet, override au plus près). Les clés sont
    normalisées comme les étiquettes, sinon `Front:` en conf ne router ait jamais
    rien — et l'erreur serait invisible.
    """
    out = {}
    for meta in (client_meta or {}, project_meta or {}):
        table = (meta or {}).get(CONF_KEY) or {}
        if not isinstance(table, dict):
            continue
        for tag, role in table.items():
            k, v = _norm(tag), str(role or "").strip().lower()
            if k and v:
                out[k] = v
    return out


def suggest(tags, table):
    """(rôle, raison) suggéré pour un ticket, ou (None, raison).

    Plusieurs étiquettes peuvent router : on prend la PREMIÈRE dans l'ordre
    alphabétique des étiquettes qui matchent — un ordre arbitraire mais STABLE,
    et la raison nomme l'étiquette retenue ainsi que les autres candidates. Un
    départage silencieux serait pire qu'un départage arbitraire annoncé.
    """
    # La table peut venir de la conf brute : on la normalise dans tous les cas
    # (une clé « Front » en conf ne doit pas passer à côté de l'étiquette front).
    t = merge_table(None, {CONF_KEY: table if isinstance(table, dict) else {}})
    matches = sorted({_norm(x) for x in (tags or []) if _norm(x)} & set(t))
    if not matches:
        return None, ("aucune étiquette ne route" if t else
                      "aucune table de routage (meta.yml : tag_roles)")
    role = t[matches[0]]
    why = f"étiquette « {matches[0]} » → rôle {role}"
    if len(matches) > 1:
        why += f" (aussi candidates : {', '.join(matches[1:])})"
    if role not in KNOWN_ROLES:
        why += f" ⚠ rôle inconnu (agents/worker-{role}.md absent ?)"
    return role, why


def agent_file(role) -> str:
    """Chemin du fichier d'instructions du rôle, tel qu'on le cite à l'agent."""
    return f"agents/worker-{str(role or '').strip().lower()}.md"
