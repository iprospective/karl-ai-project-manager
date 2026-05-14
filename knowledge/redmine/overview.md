---
type: knowledge
product: redmine
topic: overview
created: 2026-05-14
---

# Redmine — overview technique

Stack typique : **Ruby on Rails + MySQL/PostgreSQL/SQLite + puma**. Code open-source,
souvent installé en *vendor mode* (clone git ou release tarball) plutôt qu'en gem.

## Modèles principaux (tables BDD)

| Table | Rôle | Champs texte (formatés) |
|---|---|---|
| `projects` | Projets | `description` |
| `issues` | Tickets | `description` |
| `journals` | Historique d'un ticket (notes + changes) | `notes` |
| `journal_details` | Détail d'un change d'attribut (ancien→nouveau) | `value` (mais souvent non-formaté) |
| `wiki_pages` | Métadonnées d'une page wiki | (titre uniquement) |
| `wiki_contents` | Contenu courant d'une page wiki | `text` |
| `wiki_content_versions` | Historique des pages wiki | `data` (longblob, parfois gzip) — accédé via `.text` getter |
| `messages` | Forum posts | `content` |
| `comments` | Comments polymorphiques (utilisés peu) | `content` |
| `news` | Annonces projet | `description` |
| `documents` | Documents projet | `description` |
| `attachments` | Pièces jointes | `description` (court) — fichier sur disque |
| `custom_fields` | Définition des champs custom | `description` |
| `custom_values` | Valeurs custom des objets | `value` (formaté si field_format=text) |
| `settings` | Paramètres globaux | clé `welcome_text` notamment |

Champ central : **`settings.text_formatting`** = `textile` ou `common_mark` (ou `markdown` selon
version) → détermine comment tout le contenu texte est rendu.

## Terminologie

- **Tracker** : type de ticket (bug, feature, support, task…)
- **Status** : état d'un ticket. Configurable par instance (workflow par tracker).
- **Priority** : priorité (low/normal/high/urgent), enumeration personnalisable.
- **Issue Category** : catégorisation interne à un projet (orthogonale aux trackers).
- **Version** : milestone/jalon. Tickets s'y attachent via `fixed_version_id`.
- **Journal** : entrée d'historique d'un ticket. Une journal peut contenir une `notes`
  ET/OU des `details` (changements d'attributs). Le user "poste une note" = créer un
  journal avec notes non vide.
- **Wiki Compression** : `Setting.wiki_compression` peut être `''` ou `gzip` →
  contrôle si les nouvelles versions wiki sont stockées compressées (Zlib::Deflate).
  Le getter `.text` décompresse à la volée.

## Structure typique d'install

Sur l'instance auditée (`/home/tasks/redmine-git`) :

```
redmine-git/
├── app/                   # controllers, models, views
├── bin/                   # binstubs (rails, bundle, rake)
├── config/                # database.yml, configuration.yml, environments/
├── db/                    # migrations
├── lib/
│   ├── redmine/           # core (formatters, scm, etc.)
│   └── tasks/             # rake tasks (où installer un script de migration)
├── plugins/               # symlink vers ../plugins-enabled
├── public/                # assets précompilés
├── files/                 # symlink vers ../files (pièces jointes)
├── log/                   # logs Rails
├── tmp/                   # pids, cache, sessions
└── Gemfile / Gemfile.lock
```

Les liens `plugins/`, `files/`, `log/`, `tmp/` sont souvent **symlinks relatifs**
vers `../<dossier>` pour partager entre versions/installs côte à côte.

## Démarrage typique

```bash
# Souvent un script start.sh user-side
cd /home/tasks/prod
bundle exec rails server -u puma -e production -p 3000
```

Avec rbenv usuel pour piloter la version Ruby (`.ruby-version` dans le dossier).
Env vars critiques : `SECRET_KEY_BASE` (Rails 8 le RAISE si absent).

## Plugins observés (instance iprospective)

| Plugin | Rôle | Note |
|---|---|---|
| `easy_baseline`, `easy_gantt`, `easy_gantt_pro` | Suite Easy (gantt avancé) | Patche `IssueRelation` |
| `redmine_editauthor` | Permet d'éditer l'auteur d'une note | Patches sur Journal |
| `redmine_gantt_drag` | Drag&drop sur le gantt | |
| `redmine_issue_dynamic_edit` | Édition inline des champs ticket | |
| `redmine_issue_templates` | Templates de tickets par tracker | |
| `redmine_wiki_extensions` | Macros wiki additionnelles, emoticons | Peut introduire des `{{...}}` propres |
| `view_customize` | Injection JS/CSS conditionnelle | |

## Versions de Redmine et conséquences

| Version | Point notable |
|---|---|
| < 4.1 | Pas de support CommonMark — Markdown limité (Redcarpet) |
| ≥ 4.1 | CommonMark supporté côté setting → migration Textile envisageable |
| ≥ 5.x | Rails 6.1+, Ruby ≥ 2.7 |
| ≥ 6.0 | Rails 7 |
| 6.1 | Rails 8.1, Ruby ≥ 3.2 |
