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


def add_issue_note(issue_id, note, timeout=20):
    """Ajoute une note (journal) à une issue via PUT `notes`. Sys.exit si échec."""
    url, key = redmine_creds()
    payload = {"issue": {"notes": note}}
    code, body = http_json("PUT", f"{url}/issues/{issue_id}.json", key, payload, timeout=timeout)
    if code not in (200, 204):
        sys.exit(f"ERREUR Redmine HTTP {code} sur note de #{issue_id} : {body.get('_error', '')}")
    return True


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
                         extra_custom_fields=None, parent_issue_id=None, timeout=20):
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
