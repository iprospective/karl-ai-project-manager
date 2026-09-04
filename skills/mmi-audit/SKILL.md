---
name: mmi-audit
description: Route TOUTE demande d'audit vers le projet PM `iprospective/audits` et son outillage rejouable (repo `ai-audits`), au lieu d'une analyse ad hoc jetable. Déclenche dès qu'il s'agit d'auditer, d'analyser la sécurité, de faire un état des lieux ou de fingerprinter quoi que ce soit — site web, WordPress/PrestaShop/Dolibarr, serveur, infra, DNS, stack mail, hébergement, conformité — **y compris quand la demande arrive depuis un autre projet PM**, qui est le cas de loin le plus fréquent et celui qui échoue. Usage : "/mmi-audit", ou langage naturel "fais-moi un audit de X", "audite ce site", "analyse la sécurité de Y", "état des lieux de ce serveur", "check la conf de Z", "scan de surface".
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion
---

# Skill : mmi-audit

**Routage, pas méthodologie.** Ce skill dit *où* va un audit et *dans quel ordre* on
procède. La méthodologie de domaine vit dans le repo `ai-audits`
(`audits-common/METHODOLOGY.md`, `PLAYBOOK-*.md`, `knowledge/`) — conformément à
`skills/README.md` § Convention, qui réserve `skills/` aux skills transverses au PM et
renvoie les domaines spécifiques à leur propre repo.

## Quand déclencher

- « fais-moi un audit de X », « audite ce site / ce serveur », « analyse la sécurité de »
- « état des lieux », « cartographie », « scan », « fingerprint », « pentest », « recon »
- « check la conf de », « qu'est-ce qui cloche sur », « est-ce que c'est bien configuré »
- une demande de **conformité** (RGPD/CNIL, LCEN, en-têtes, TLS, DNS)
- `/mmi-audit`

**Le cas qui échoue, et pour lequel ce skill existe :** la demande arrive depuis un
**autre workspace** (`communication`, `infrastructure`, un projet client…). L'onboarding
NORMS remonte le `.mmi-pm` du workspace courant, jamais celui du projet `audits` — donc
sa convention n'est pas lue et l'agent part sur une analyse à la main. C'est exactement
ce qui s'est produit sur RM2900 (voir § Pourquoi).

## Où se trouve le système d'audit

| Élément | Chemin |
|---|---|
| Projet PM | `iprospective/audits` (Redmine `audits`) |
| Convention | `project/overview.md` § « Convention — tout nouvel audit » |
| Workspace de code | `/zfs/workspaces/iprospective/audits` |
| Worktree | `envs/ai-audits-dev/` (repo `ai-audits`) |
| Spec d'arborescence | `audits-common/STRUCTURE.md` — entité → fonction → site → session `<YYYY-MM-DD>-<type>` |

## Procédure — dans cet ordre

### 1. Lire l'existant AVANT de mesurer quoi que ce soit

**Étape non négociable.** Un finding déjà ouvert redécouvert à la main est une perte
sèche, et pire : il fait passer une régression non traitée pour une découverte.

```bash
A=/zfs/workspaces/iprospective/audits/envs/ai-audits-dev
cat $A/clients/<entité>/INDEX.md                       # fonctions + sessions connues
cat $A/clients/<entité>/<fonction>/INDEX.md            # sites + findings ouverts
cat $A/clients/<entité>/<fonction>/<site>/state.md     # snapshot vivant du site
cat $A/clients/<entité>/<fonction>/<date>-<type>/FINDINGS.md
```

Si des findings sont ouverts : ils se **re-statuent** dans la colonne « Statut session
+N » de la session d'origine. On n'en crée pas de doublon.

### 2. Créer le ticket dans le projet `audits`

```bash
cd /zfs/workspaces/iprospective/audits
pm-task-add.py --project iprospective/audits --type security|research \
  --title "..." --description-file <fichier>
```

Le ticket décrit le **périmètre et les paramètres** (cible, set comparé, pondération) —
la convention exige un audit paramétrable et rejouable, pas une analyse figée.

### 3. Ouvrir une session

```bash
$A/audits-common/scripts/new-audit-session.sh    # → clients/<E>/<F>/<YYYY-MM-DD>-<type>/
```

### 4. Passer les scripts existants, pas des commandes ad hoc

```
recon-dns.sh  recon-headers.sh  recon-subdomains.sh  recon-http-probe.sh
recon-resolve.sh  recon-wordpress.sh  recon-dolibarr.sh
```

`knowledge/` couvre déjà : `wordpress`, `prestashop`, `dolibarr`, `nextcloud`,
`rocketchat`, `roundcube`, `symfony`. **Lire la fiche produit avant d'auditer** : elle
contient les contrôles connus et les faux positifs déjà écartés.

Si le type d'audit n'existe pas encore → ouvrir un ticket « Type d'audit `<slug>` »
sur le modèle de RM2419 (cartographie d'infra) ou RM2503 (stack-mail) : playbook +
scripts + knowledge + fixes, exposé en web-ui.

### 5. Consigner et rafraîchir

- findings dans `FINDINGS.md` (IDs continus `F0NN`, sévérité 🔴/🟠/🟡/🟢)
- `state.md` du site : `products`, `findings_open`, `last_observed`
- `refresh-indexes.py` pour régénérer les INDEX

## La règle de partage entre projets

> **Les findings vont dans `audits`. La remédiation va dans le projet propriétaire de
> l'objet audité.**

Un audit de site plaquette produit donc :

| Volet | Où |
|---|---|
| sécurité, conformité, surface exposée | ticket + session dans `audits` |
| correctifs à appliquer sur le site | tickets dans le projet du site (`communication`, projet client…) |
| SEO, performance, contenu, positionnement | projet du site — **hors périmètre `audits`** |

Les deux se lient avec `pm-task-link.py … --type relates`.

## Pourquoi ce skill existe

Le 2026-08-31, l'audit de `www.iprospective.fr` a été mené entièrement à la main depuis
le workspace `communication` (RM2900). Résultat :

- **F006** (« aucun en-tête de sécurité HTTP ») était déjà ouvert depuis la session
  `2026-05-10-recon`. Redécouvert 3,5 mois plus tard sans que rien ne signale qu'il
  s'agissait d'une régression non traitée.
- `recon-wordpress.sh` existait, et son en-tête documente précisément le motif retrouvé
  à la main (énumération via `/wp-json/wp/v2/users` + `xmlrpc.php`, découvert sur
  dercya.com le 2026-05-09). Il n'a pas été passé.
- Les constats produits n'étaient ni rejouables, ni raccordés à `state.md` /
  `FINDINGS.md`.

Rattrapage : RM2910. Ticket de ce skill : RM2911.

## Références

- `iprospective/audits` → `project/overview.md` § « Convention — tout nouvel audit »
- `audits-common/STRUCTURE.md`, `METHODOLOGY.md`, `PLAYBOOK-recon.md`
- `skills/README.md` § Convention (transverse PM vs. domaine)
- RM2004 (ticket fondateur de la convention), RM2419, RM2503 (types d'audit existants)
