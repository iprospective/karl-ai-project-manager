> 📂 **Module `audits` — quand lire ceci :** on me demande un audit, une analyse de
> sécurité, un état des lieux, une cartographie, un scan ou un contrôle de conformité —
> **quel que soit le projet depuis lequel la demande arrive**.
> **Outils :** skill `mmi-audit` · `new-audit-session.sh` · `recon-*.sh` · `refresh-indexes.py` · **Préchargé par :** —.

## Audits — le système, pas l'analyse ad hoc

Un audit **n'est jamais** une analyse improvisée dans le projet courant. iProspective
possède un système d'audit dédié : un projet PM, une arborescence de données, un
outillage rejouable et un référentiel de connaissances par produit. Toute demande
d'audit s'y rattache.

| Élément | Où |
|---|---|
| Projet PM | `iprospective/audits` (Redmine `audits`) |
| Convention de projet | son `project/overview.md` § « Convention — tout nouvel audit » |
| Workspace / repo de code | `/zfs/workspaces/iprospective/audits`, repo `ai-audits` |
| Worktree de travail | `envs/ai-audits-dev/` |
| Spec d'arborescence | `audits-common/STRUCTURE.md` |

La convention du projet impose trois choses à tout **nouveau type** d'audit :
méthodologie **paramétrable** (paramètres d'entrée explicites : cible, set comparé,
pondération), **rejouable** sans réécriture, et **exposée en interface web** (formulaire
→ rapport), pas seulement en CLI. Ticket fondateur : RM2004.

### Arborescence des données (spec v2)

```
clients/<entité>/<fonction>/<site>/state.md          # snapshot vivant
clients/<entité>/<fonction>/<YYYY-MM-DD>-<type>/     # session datée
                                    ├── FINDINGS.md
                                    ├── REPORT.md
                                    └── REPORT-CLIENT.md
```

`<fonction>` = `site`, `mail`, `infra`… ; `<type>` de session = `recon` (défaut),
`stack-mail`, etc.

## Ordre d'opération — non négociable

### 1. Lire l'existant AVANT de mesurer

C'est **le** point qui échoue, et il coûte cher : un finding déjà ouvert et
« redécouvert » à la main est présenté comme une trouvaille alors que c'est une
**régression non traitée** — le contraire de l'information utile.

```bash
A=/zfs/workspaces/iprospective/audits/envs/ai-audits-dev
cat $A/clients/<entité>/INDEX.md                        # fonctions + sessions connues
cat $A/clients/<entité>/<fonction>/INDEX.md             # sites + findings ouverts
cat $A/clients/<entité>/<fonction>/<site>/state.md      # produits, surface, findings ouverts
cat $A/clients/<entité>/<fonction>/<session>/FINDINGS.md
```

Un finding déjà ouvert se **re-statue** dans la colonne « Statut session +N » de sa
session d'origine. On n'en crée jamais de doublon dans une nouvelle session.

### 2. Créer le ticket dans `iprospective/audits`

Le ticket décrit le **périmètre et les paramètres**, pas la conclusion. Type `security`
ou `research`. Référence projet **précise** (`iprospective/audits`), jamais le slug nu —
cf. tripwire #14.

### 3. Ouvrir une session

`audits-common/scripts/new-audit-session.sh` → `clients/<E>/<F>/<YYYY-MM-DD>-<type>/`.

### 4. Passer l'outillage existant, pas des commandes improvisées

| Script | Couvre |
|---|---|
| `recon-dns.sh` | apex, MX, SPF/DKIM/DMARC, CAA, DNSSEC |
| `recon-headers.sh` | en-têtes de sécurité HTTP |
| `recon-subdomains.sh` | énumération via crt.sh |
| `recon-http-probe.sh` | surface HTTP |
| `recon-resolve.sh` | résolution / cohérence DNS |
| `recon-wordpress.sh` | version, plugins, thèmes, users, xmlrpc, chemins sensibles |
| `recon-dolibarr.sh` | fingerprint Dolibarr |

`knowledge/` porte le référentiel par produit — `wordpress`, `prestashop`, `dolibarr`,
`nextcloud`, `rocketchat`, `roundcube`, `symfony`. **Lire la fiche du produit avant
d'auditer** : elle contient les contrôles connus et les faux positifs déjà écartés.
`audits-common/fixes/` porte les correctifs types (apache, nginx, dns-caa, dns-dmarc-spf).

Le **détail méthodologique** vit dans le repo `ai-audits`
(`audits-common/METHODOLOGY.md`, `PLAYBOOK-<type>.md`), pas ici : NORMS dit *où* et
*dans quel ordre*, le repo de domaine dit *comment*.

**Type d'audit inexistant** ⇒ ne pas improviser : ouvrir un ticket
« Type d'audit `<slug>` » sur le modèle de RM2419 (cartographie d'infra) ou RM2503
(stack-mail) — playbook + scripts + knowledge + fixes + web-ui.

### 5. Consigner et rafraîchir

- findings dans `FINDINGS.md` : IDs continus `F0NN`, sévérité 🔴 critique / 🟠 élevé /
  🟡 moyen / 🟢 info, et une ligne de statut par session ultérieure ;
- `state.md` du site : `products`, `findings_open`, `last_observed` ;
- `refresh-indexes.py` pour régénérer les INDEX de fonction et de client.

## Règle de partage entre projets

> **Les findings vont dans `audits`. La remédiation va dans le projet propriétaire de
> l'objet audité.**

| Volet | Projet |
|---|---|
| sécurité, conformité, surface exposée | `iprospective/audits` |
| correctifs à appliquer | projet du site / du serveur (`communication`, projet client…) |
| SEO, performance, contenu, positionnement | projet propriétaire — **hors périmètre `audits`** |

Les deux se lient en `relates` (`pm-task-link`, cf. `modules/task-links.md`).

Le **livrable documentaire** de l'audit suit par ailleurs la règle de format portable de
`modules/redmine-sync.md` : markdown en repo, synchronisé wiki, jamais un artefact
LLM-spécifique.

## Incident fondateur

2026-08-31, RM2900 — audit de `www.iprospective.fr` mené à la main depuis le workspace
`communication` :

- **F006** (« aucun en-tête de sécurité HTTP ») était ouvert depuis la session
  `2026-05-10-recon` ; redécouvert 3,5 mois plus tard sans que rien ne signale la
  régression ;
- `recon-wordpress.sh` existait et documentait exactement le motif retrouvé au curl
  (énumération via `/wp-json/wp/v2/users` + `xmlrpc.php`, découvert sur dercya.com le
  2026-05-09) — il n'a pas été passé ;
- les constats n'étaient ni rejouables, ni raccordés à `state.md` / `FINDINGS.md`.

Cause : l'onboarding ne remonte que le `.mmi-pm` du **workspace courant**, donc la
convention du projet `audits` n'était jamais lue. D'où ce module et son déclencheur
KERNEL. Rattrapage : RM2910. Skill de routage : RM2911.
