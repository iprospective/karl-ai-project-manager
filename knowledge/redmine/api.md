---
type: knowledge
product: redmine
topic: api
created: 2026-05-14
---

# Redmine — API REST

## Authentification

Trois modes (au choix) :
- Query string : `?key=<api_key>` (rapide pour curl/tests)
- Header : `X-Redmine-API-Key: <api_key>`
- Basic auth : `<api_key>:random`

La clé est trouvable sur `/my/account` côté UI (section "API access key").

## Endpoints essentiels

```
GET    /users/current.json                       # qui suis-je
GET    /projects.json                            # projets visibles
GET    /projects/{id-or-identifier}.json         # détail projet
GET    /projects/{id}/wiki/index.json            # index wiki d'un projet
GET    /projects/{id}/wiki/{title}.json          # page wiki
PUT    /projects/{id}/wiki/{title}.json          # créer/maj page wiki

GET    /issues.json?project_id=X&status_id=Y     # liste tickets
GET    /issues/{id}.json?include=journals,attachments,relations  # détail
POST   /issues.json                              # créer ticket
PUT    /issues/{id}.json                         # update + note (via "notes")
DELETE /issues/{id}.json                         # delete

POST   /uploads.json (Content-Type octet-stream) # upload — renvoie un token
                                                  # à passer dans PUT/POST {issue/wiki_page: {uploads: [{token, filename, content_type}]}}
```

## Payload exemple : poster une note + changer status + attacher fichier

```bash
# 1. upload du fichier
curl -X POST -H "Content-Type: application/octet-stream" \
  --data-binary @fichier.md \
  "https://redmine.example.com/uploads.json?key=$API_KEY"
# → {"upload":{"token":"abc...xyz"}}

# 2. PUT issue
curl -X PUT -H "Content-Type: application/json" \
  -d '{"issue":{
    "notes":"Texte de la note",
    "status_id":9,
    "assigned_to_id":5,
    "uploads":[{"token":"abc...xyz","filename":"fichier.md","content_type":"text/markdown"}]
  }}' \
  "https://redmine.example.com/issues/1234.json?key=$API_KEY"
```

**`update_column` côté API n'existe pas** — toute écriture passe par les
validations + callbacks. C'est l'inverse de ce qu'on fait en rake script.

## Récupérer les journals (notes + changes)

`GET /issues/{id}.json?include=journals` → tableau `journals` :

```json
{
  "issue": {
    "id": 1234,
    "journals": [
      {"id": 5067, "user": {"id":5,"name":"Mathieu Moulin"}, "notes": "...", "created_on": "...",
       "details": [{"property":"attr","name":"status_id","old_value":"9","new_value":"11"}, ...]},
      ...
    ]
  }
}
```

Les **`details`** structurent les changements d'attributs (status_id, assigned_to_id,
priority_id, subject, etc.) — utile pour reconstituer l'historique sans re-fetch.

## Polling multi-tour

Pour suivre les nouveaux journaux depuis la dernière consultation : mémoriser
`last_journal_id`, puis filtrer côté client sur `j.id > last_journal_id`.
Il n'y a **pas** de paramètre `since` natif sur `journals` (filtrage côté client).

## Permissions — piège silencieux

Le compte API doit avoir les **bonnes permissions** sur le projet/tracker :

| Action | Permission Redmine requise |
|---|---|
| Lire issue | "View issues" |
| Poster une note | "Add notes" |
| Changer statut/assigné/priorité | **"Edit issues"** |
| Upload pièce jointe (sur un ticket) | "Edit issues" + "Add attachments" |
| Créer/modifier page wiki | "Edit wiki pages" |
| Lire wiki | "View wiki pages" |

⚠ **Comportement piégeux** : si la perm "Edit issues" manque, Redmine accepte le
PUT, renvoie **HTTP 204 No Content** (apparente réussite), mais **drop silencieusement**
tous les attributs autres que `notes`. La note est créée, mais le `status_id` /
`assigned_to_id` ne changent pas. Aucune erreur retournée.

**Détection** : refaire un GET après le PUT et comparer l'état attendu. Si le statut
n'a pas bougé alors qu'on l'a demandé → c'est probablement la permission.

**Fix** : ajouter le compte API dans un groupe "Managers" ou créer un rôle "AI Agent"
avec les perms nécessaires.

## Mapping NORMS ↔ Redmine status (instance iprospective)

Configuration spécifique de cette instance — IDs Redmine variables d'une instance à l'autre.

> **Source canonique** : `redmine.reference.yml` (racine du repo PM) + le binding réel
> `redmine-post-note.py::NORMS_TO_REDMINE_STATUS`. Revalidé via
> `scripts/redmine-config-check.py` (NORMS § « Synchronisation de la configuration
> Redmine »). Le snippet ci-dessous est documentaire — en cas de doute, c'est le
> live (et la référence) qui font foi.

```python
NORMS_TO_REDMINE_STATUS = {
    "a_etudier_chiffrer":       8,  # "A étudier / Qualifier"
    "etude_chiffrage_en_cours": 14, # "Etude en cours"
    "a_faire":                  12, # "A Faire"
    "en_cours":                  2, # "En cours"
    "a_tester_verifier":         9, # "A tester/vérifier demandeur"
    "a_corriger":               11, # "A corriger/finir"
    "ferme":                    18, # "Fermé"  (seul statut clos ; toutes les
                                    #  variantes ferme:* y retombent, la nuance
                                    #  est portée par le CF 11 « Raison Fermé »)
}
```

Pour une nouvelle instance : `GET /issue_statuses.json?key=...` pour récupérer les IDs,
puis `scripts/redmine-config-check.py --dump` pour régénérer un squelette de référence.

## Tracker → type de tâche (interne)

```python
TRACKER_TO_TYPE = {
    "bug": "bugfix",
    "feature": "feature",
    "support": "assistance",
    "task": "maintenance",
}
```

À adapter selon les trackers configurés de l'instance cible.

## Format de retour des champs texte selon `text_formatting`

L'API renvoie **le texte brut** stocké en BDD (pas de rendu HTML). Le client (UI Redmine
ou tiers) doit interpréter selon le `text_formatting` global. Pour générer du contenu
côté API, **toujours produire dans le format configuré** de l'instance — ce qui implique
de connaître le setting (`GET /settings.json` réservé aux admins).
