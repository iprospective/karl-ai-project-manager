"""redmine_utils — Helpers partagés pour interagir avec l'API Redmine.

Centralise :
- résolution des credentials (.env)
- détection du custom field `IA` (mutex entre tickets Redmine purs et
  tickets PM-trackés, cf. NORMS « Filtrage IA »)
- helpers HTTP simples

Aucune logique métier PM ici — uniquement de l'I/O Redmine.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_REFERENCE_FILE = Path(__file__).resolve().parent.parent / "redmine.reference.yml"
_REFERENCE_CACHE = None

# Fallback minimal si redmine.reference.yml est introuvable/illisible — garde les
# transitions critiques fonctionnelles même sans le fichier de référence.
_FALLBACK_STATUS_IDS = {
    "a_etudier_chiffrer": 8, "etude_chiffrage_en_cours": 14, "a_faire": 12,
    "en_cours": 2, "a_tester_dev": 19, "a_tester_demandeur": 9, "a_mep": 3,
    "en_mep": 20, "en_pause": 13, "a_corriger": 11, "ferme": 18,
}
_FALLBACK_STATUS_ALIASES = {"a_tester_verifier": "a_tester_demandeur"}
# Raisons de fermeture → toutes vers le statut `ferme` (id porté par la réf).
_CLOSE_REASONS = ("resolu", "abandonne", "wont_fix", "hors_perimetre", "invalide", "doublon")


def load_reference():
    """Charge redmine.reference.yml (les IDs Redmine bindés). Cache mémoire.

    Retourne un dict (sections custom_fields/statuses/status_aliases/trackers/
    priorities/activities) ou {} si le fichier est absent/illisible (les helpers
    retombent alors sur leurs fallbacks).
    """
    global _REFERENCE_CACHE
    if _REFERENCE_CACHE is not None:
        return _REFERENCE_CACHE
    try:
        import yaml
        _REFERENCE_CACHE = yaml.safe_load(_REFERENCE_FILE.read_text(encoding="utf-8")) or {}
    except Exception:  # OSError, ImportError, yaml.YAMLError → fallback silencieux
        _REFERENCE_CACHE = {}
    return _REFERENCE_CACHE


def cf_id_by_name(name):
    """ID du custom field nommé `name` d'après la référence, ou None."""
    for cid, spec in (load_reference().get("custom_fields") or {}).items():
        if isinstance(spec, dict) and spec.get("name") == name:
            return cid
    return None


# Fallback si la référence est absente/incomplète (cf. redmine.reference.yml ::
# type_to_activity, source de vérité). Garde la convention vivante hors-fichier.
#   31 Developpement/Feature · 16 Développement/Debug · 30 Développement/Refacto/Clean
#   13 SysAdmin/Conf/Debug · 10 Audit/Analyse · 11 Assistance · 18 Autre
_FALLBACK_TYPE_TO_ACTIVITY = {
    "feature": 31, "bugfix": 16, "maintenance": 30, "infrastructure": 13,
    "research": 10, "assistance": 11, "autre": 18,
}
_DEFAULT_ACTIVITY_ID = 18  # "Autre"


def activity_for_type(task_type):
    """Activité de temps Redmine (id) pour un `type` de tâche NORMS.

    Lit `type_to_activity` de la référence (source unique), retombe sur la table
    fallback puis sur 18 « Autre ». Cf. NORMS § « Journalisation par commit ».
    """
    key = (task_type or "").strip().lower()
    mapping = load_reference().get("type_to_activity") or _FALLBACK_TYPE_TO_ACTIVITY
    return mapping.get(key, _FALLBACK_TYPE_TO_ACTIVITY.get(key, _DEFAULT_ACTIVITY_ID))


def status_aliases():
    """Mapping {statut_déprécié: statut_canonique} depuis la référence (+ fallback)."""
    ref = load_reference().get("status_aliases")
    return dict(ref) if isinstance(ref, dict) and ref else dict(_FALLBACK_STATUS_ALIASES)


def normalize_status(status):
    """Normalise un statut NORMS (résout les alias dépréciés). Idempotent."""
    if not status:
        return status
    base, _, reason = status.partition(":")
    canon = status_aliases().get(base, base)
    return f"{canon}:{reason}" if reason else canon


def status_ids():
    """Mapping {statut_NORMS_canonique: id_Redmine} depuis la référence (+ fallback)."""
    ref = load_reference().get("statuses")
    return dict(ref) if isinstance(ref, dict) and ref else dict(_FALLBACK_STATUS_IDS)


def status_map():
    """Mapping complet {statut_ou_variante: id_Redmine} pour POST/PUT Redmine.

    Inclut : les statuts canoniques, les alias dépréciés, et les variantes
    `ferme:<raison>` (toutes vers l'id du statut `ferme`). C'est la table que
    redmine-post-note.py consomme.
    """
    ids = status_ids()
    out = dict(ids)
    ferme_id = ids.get("ferme")
    if ferme_id is not None:
        for reason in _CLOSE_REASONS:
            out[f"ferme:{reason}"] = ferme_id
    for alias, canon in status_aliases().items():
        if canon in ids:
            out[alias] = ids[canon]
    return out


def valid_statuses():
    """Ensemble des statuts NORMS acceptés en écriture (canoniques + alias dépréciés)."""
    return set(status_ids()) | set(status_aliases())


def redmine_creds():
    """Retourne (url, key). Sys.exit si manquants."""
    url = os.environ.get("REDMINE_URL", "").rstrip("/")
    key = os.environ.get("REDMINE_USER_MAIN_API_KEY") or os.environ.get("REDMINE_API_KEY")
    if not (url and key):
        sys.exit("ERREUR : REDMINE_URL et REDMINE_USER_MAIN_API_KEY requis (.env)")
    return url, key


def get_ia_cf_id():
    """ID du custom field `IA` côté Redmine (configuré dans `.env :: REDMINE_CF_IA_ID`).

    Retourne `int` ou `None` si non configuré. Quand None, le filtre IA est
    désactivé (mode rétrocompat — tous les tickets sont considérés trackables).
    """
    val = (os.environ.get("REDMINE_CF_IA_ID") or "").strip()
    return int(val) if val.isdigit() else None


def issue_is_ia_tagged(issue):
    """True si le ticket Redmine porte le tag IA (custom field `IA` rempli).

    Si `REDMINE_CF_IA_ID` n'est pas configuré, retourne True (mode non filtré).
    Sinon cherche un custom_field avec cet id dont la valeur est non-vide.
    """
    cf_id = get_ia_cf_id()
    if cf_id is None:
        return True
    for cf in (issue.get("custom_fields") or []):
        if cf.get("id") != cf_id:
            continue
        v = cf.get("value")
        if v is None or v == "" or v == []:
            return False
        return True
    return False


def http_json(method, url, key, payload=None, timeout=20):
    """Requête HTTP JSON simple. Retourne (status_code, body_dict_or_error)."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "X-Redmine-API-Key": key,
                 "Accept": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode(errors="replace")[:500]
        except Exception:
            err_body = ""
        return e.code, {"_error": err_body}


def fetch_issue(issue_id, include=None):
    """Fetch un ticket avec inclusions optionnelles."""
    url, key = redmine_creds()
    qs = f"?include={include}" if include else ""
    code, body = http_json("GET", f"{url}/issues/{issue_id}.json{qs}", key)
    if code != 200:
        sys.exit(f"ERREUR Redmine HTTP {code} pour issue #{issue_id} : {body.get('_error', '')}")
    return body.get("issue", {})


def list_issues(params=None, limit=25, timeout=20):
    """Liste des issues via `/issues.json` avec filtres Redmine arbitraires.

    `params` : dict de filtres natifs Redmine (ex: {"assigned_to_id": "me",
    "status_id": "open", "sort": "updated_on:desc"}). `limit` borne le retour.
    Retourne une liste de dicts issue (vide si aucun). Sys.exit si HTTP != 200.
    """
    url, key = redmine_creds()
    qp = dict(params or {})
    qp.setdefault("limit", limit)
    qs = urllib.parse.urlencode(qp)
    code, body = http_json("GET", f"{url}/issues.json?{qs}", key, timeout=timeout)
    if code != 200:
        sys.exit(f"ERREUR Redmine HTTP {code} sur /issues : {body.get('_error', '')}")
    return body.get("issues", [])


def search_issues(query, limit=15, timeout=20):
    """Recherche plein-texte via `/search.json` (scope issues uniquement).

    Retourne une liste de résultats {id, title, type, url, datetime, description}.
    Sys.exit si HTTP != 200.
    """
    url, key = redmine_creds()
    qs = urllib.parse.urlencode({"q": query, "issues": 1, "limit": limit})
    code, body = http_json("GET", f"{url}/search.json?{qs}", key, timeout=timeout)
    if code != 200:
        sys.exit(f"ERREUR Redmine HTTP {code} sur /search : {body.get('_error', '')}")
    return body.get("results", [])


def list_time_entries(params=None, limit=100, timeout=20):
    """Liste des saisies de temps via `/time_entries.json` avec filtres natifs.

    `params` ex: {"user_id": 5, "spent_on": "2026-06-02"}. Retourne une liste de
    dicts time_entry (chacun avec hours, user, issue, custom_fields…).
    """
    url, key = redmine_creds()
    qp = dict(params or {})
    qp.setdefault("limit", limit)
    qs = urllib.parse.urlencode(qp)
    code, body = http_json("GET", f"{url}/time_entries.json?{qs}", key, timeout=timeout)
    if code != 200:
        sys.exit(f"ERREUR Redmine HTTP {code} sur /time_entries : {body.get('_error', '')}")
    return body.get("time_entries", [])


def find_users(name, limit=5, timeout=20):
    """Recherche d'utilisateurs Redmine par fragment (login/nom/mail).

    Best-effort : nécessite les droits admin sur la clé API. Retourne une liste
    de dicts {id, firstname, lastname, login, ...} ou [] si non autorisé / aucun.
    """
    url, key = redmine_creds()
    qs = urllib.parse.urlencode({"name": name, "limit": limit})
    code, body = http_json("GET", f"{url}/users.json?{qs}", key, timeout=timeout)
    if code != 200:
        return []
    return body.get("users", [])


def add_issue_note(issue_id, note, timeout=20):
    """Ajoute une note (journal) à une issue via PUT `notes`. Sys.exit si échec."""
    url, key = redmine_creds()
    payload = {"issue": {"notes": note}}
    code, body = http_json("PUT", f"{url}/issues/{issue_id}.json", key, payload, timeout=timeout)
    if code not in (200, 204):
        sys.exit(f"ERREUR Redmine HTTP {code} sur note de #{issue_id} : {body.get('_error', '')}")
    return True


def update_issue_fields(issue_id, *, custom_fields=None, estimated_hours=None,
                        notes=None, timeout=20):
    """PUT générique sur une issue : custom_fields + estimated_hours + note.

    `custom_fields` : list[{id, value}]. `estimated_hours` : float (heures natives
    Redmine). `notes` : str optionnel (journalise le changement). N'envoie que les
    attributs fournis. Retourne (ok: bool, err: str).

    ⚠ Piège permissions (cf. knowledge/redmine/api.md) : sans « Edit issues »,
    Redmine renvoie 204 mais *drop* silencieusement les attributs ≠ notes. Ce
    helper ne re-vérifie pas ; l'appelant le fait s'il a besoin de la garantie.
    """
    url, key = redmine_creds()
    issue = {}
    if custom_fields:
        issue["custom_fields"] = custom_fields
    if estimated_hours is not None:
        issue["estimated_hours"] = estimated_hours
    if notes:
        issue["notes"] = notes
    if not issue:
        return True, ""
    code, body = http_json("PUT", f"{url}/issues/{issue_id}.json", key,
                           {"issue": issue}, timeout=timeout)
    if code not in (200, 204):
        return False, f"HTTP {code} : {body.get('_error', '')[:300]}"
    return True, ""


def create_time_entry(issue_id, *, hours, activity_id, spent_on=None,
                      comments=None, custom_fields=None, timeout=20):
    """Crée une saisie de temps (`POST /time_entries.json`) sur une issue.

    `hours` : float (> 0 attendu côté Redmine). `activity_id` : id d'activité
    (cf. redmine.reference.yml :: activities). `spent_on` : 'YYYY-MM-DD' (défaut
    aujourd'hui côté Redmine si None). `comments` : str. `custom_fields` :
    list[{id, value}] (ex: CF 16 Tokens). Retourne (ok, time_entry_id_or_err).
    """
    url, key = redmine_creds()
    entry = {"issue_id": issue_id, "hours": round(float(hours), 2),
             "activity_id": activity_id}
    if spent_on:
        entry["spent_on"] = spent_on
    if comments:
        entry["comments"] = comments
    if custom_fields:
        entry["custom_fields"] = custom_fields
    code, body = http_json("POST", f"{url}/time_entries.json", key,
                           {"time_entry": entry}, timeout=timeout)
    if code not in (200, 201):
        return False, f"HTTP {code} : {body.get('_error', '')[:300]}"
    return True, body.get("time_entry", {}).get("id")


def set_issue_ia_tag(issue_id, value="IA"):
    """Set le CF IA sur un ticket. `value=''` ou `None` retire le tag."""
    cf_id = get_ia_cf_id()
    if cf_id is None:
        sys.exit("ERREUR : REDMINE_CF_IA_ID non configuré dans .env — impossible de tag")
    url, key = redmine_creds()
    payload = {"issue": {"custom_fields": [{"id": cf_id, "value": value or ""}]}}
    code, body = http_json("PUT", f"{url}/issues/{issue_id}.json", key, payload)
    if code not in (200, 204):
        sys.exit(f"ERREUR Redmine HTTP {code} : {body.get('_error', '')}")


def set_issue_parent(issue_id, parent_id):
    """Pose (ou retire) le parent natif d'une issue Redmine via `parent_issue_id`.

    `parent_id=None` détache l'issue de son parent (envoie une valeur vide, que
    Redmine interprète comme « pas de parent »). Sys.exit si le PUT échoue.
    """
    url, key = redmine_creds()
    val = parent_id if parent_id is not None else ""
    payload = {"issue": {"parent_issue_id": val}}
    code, body = http_json("PUT", f"{url}/issues/{issue_id}.json", key, payload)
    if code not in (200, 204):
        sys.exit(f"ERREUR Redmine HTTP {code} sur parent_issue_id de #{issue_id} : "
                 f"{body.get('_error', '')}")


def create_redmine_issue(*, project_id, tracker_id, priority_id, subject,
                         description="", author_id=None, tag_ia=True,
                         extra_custom_fields=None, parent_issue_id=None,
                         status_id=None, timeout=20):
    """Crée un ticket Redmine côté PM (POST + CF IA + PUT author optionnel).

    Source unique de vérité pour la création de tickets depuis le système PM.
    Le CF IA est setté par défaut — les tickets PM-créés sont IA-trackés par
    construction (cf. NORMS « Filtrage IA »).

    Args:
        project_id: int (id) ou str (identifier) du projet Redmine.
        tracker_id: int — tracker NORMS (cf. NORMS_TYPE_TO_TRACKER côté caller).
        priority_id: int — priorité Redmine (1 low … 4 urgent).
        subject: str — titre.
        description: str — corps Redmine (markdown/textile selon instance).
        author_id: int|None — si fourni, PUT après POST pour réécrire author.
            POST set toujours author=owner-de-la-clé-API ; passer un id ici
            n'a de sens que si différent de cet owner.
        tag_ia: bool — set le CF IA='IA' au POST (défaut True).
            Mettre False uniquement pour cas hors-PM (tickets externes,
            tests, migration historique).
        extra_custom_fields: list[{id, value}] — CFs additionnels (ex: target_env).
        parent_issue_id: int|None — si fourni, crée l'issue comme enfant de ce
            ticket (attribut natif Redmine `parent_issue_id`).
        status_id: int|None — statut Redmine initial. Si None (défaut), résolu
            vers `a_faire` (le statut initial canonique de la state-machine
            NORMS). Sans ça, Redmine retombe sur le statut par défaut du tracker
            (« Nouveau », id 1) qui est HORS state-machine PM → divergence avec
            le MD qui pose toujours `a_faire`. Passer un id explicite pour créer
            directement dans une autre phase (ex. `a_etudier_chiffrer`).

    Returns:
        int : rm_id du ticket créé.

    Raises:
        SystemExit : POST échoué (bloquant).
            PUT author_id échouant n'est pas bloquant — warning stderr et
            le ticket reste author=key-owner.
    """
    url, key = redmine_creds()
    payload_issue = {
        "project_id": project_id,
        "tracker_id": tracker_id,
        "priority_id": priority_id,
        "subject": subject,
        "description": description,
    }
    if parent_issue_id is not None:
        payload_issue["parent_issue_id"] = parent_issue_id
    # Statut initial : a_faire par défaut (jamais « Nouveau » du tracker, qui
    # est hors state-machine NORMS et diverge du MD posé par les callers).
    if status_id is None:
        status_id = status_ids().get("a_faire")
    if status_id is not None:
        payload_issue["status_id"] = status_id
    custom_fields = list(extra_custom_fields or [])
    if tag_ia:
        cf_ia_id = get_ia_cf_id()
        if cf_ia_id is not None:
            custom_fields.append({"id": cf_ia_id, "value": "IA"})
    if custom_fields:
        payload_issue["custom_fields"] = custom_fields

    code, body = http_json("POST", f"{url}/issues.json", key,
                           {"issue": payload_issue}, timeout=timeout)
    if code not in (200, 201):
        sys.exit(f"ERREUR Redmine HTTP {code} sur POST /issues : "
                 f"{body.get('_error', '')[:500]}")
    rm_id = body["issue"]["id"]

    if author_id is not None:
        code2, body2 = http_json("PUT", f"{url}/issues/{rm_id}.json", key,
                                 {"issue": {"author_id": author_id}}, timeout=10)
        if code2 not in (200, 204):
            print(f"⚠ PUT author_id={author_id} échoué (HTTP {code2}) sur RM{rm_id} — "
                  f"ticket reste author=key-owner", file=sys.stderr)

    return rm_id
