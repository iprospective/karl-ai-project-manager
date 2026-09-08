# Gabarits de CDC complet

À copier dans le `docs/` du projet PM quand on attaque **un projet neuf par un cahier des
charges complet** (norme : `norms/src/modules/cdc.md`, § « Ouvrir un CDC »). Ne pas copier ce
README ni le dossier tel quel : `pm-cdc.py init` le fait, en renommant les fichiers avec le
ticket porteur et en remplaçant les marqueurs.

Ces gabarits sont issus d'un CDC réel (140 décisions, 124 fonctionnalités, un POC qui lit le
CDC) et de la relecture des CDC des autres projets du parc — ce qui y a servi, ce qui y a
manqué.

## Contenu

| Fichier | Rôle |
|---|---|
| `00-sommaire.md` | méthode de travail, états, plan, **critère de fin** — à remplir en premier |
| `01-perimetre.md` | le problème, le non négociable, **ce que l'agent suppose**, le hors-périmètre |
| `0N-chapitre.md` | gabarit d'un chapitre thématique |
| `1N-audit-existant.md` | gabarit d'un audit — configurations, données, solutions comparables |
| `1N-ce-qu-on-voudra-observer.md` | les mesures décidées **avant** de construire |
| `1N-comment-ce-projet-meurt.md` | les risques et leurs parades structurelles |
| `90-decisions.md` | le registre : proposition, conseil, arbitrage, état |
| `91-vrac.md` | notes verbatim et retours d'utilisateurs, tracés jusqu'à résolution |
| `92-glossaire.md` | les mots du produit, et le mot du schéma quand il diffère |
| `99-questions-ouvertes.md` | ce qui n'est pas tranché, ce que ça bloque, l'avis |
| `grille-360.md` | la grille d'axes × les cinq postures — à dérouler au temps 3 |
| `recueil-utilisateurs.md` | trame d'entretien, canaux, circuit vrac → décision |
| `dict/*.yml` | les treize tables du dictionnaire, vides, avec leurs conventions |

Les fichiers `0N-` et `1N-` sont des **gabarits à dupliquer** (`02-…`, `14-…`) : le `N` n'est
pas un numéro, c'est la marque d'un modèle.

## Ce qui ne change pas d'un projet à l'autre

- les **états** (✅ ❌ 🟡 🕐 ⏸) et leur sens ;
- la règle **conseiller avant de consigner** ;
- **une seule source par donnée** — le dictionnaire est la source, le chapitre est généré ;
- les **types logiques** dans `dict/champs.yml`, jamais SQL tant que le SGBD n'est pas statué ;
- l'**échelle unique** d'état d'une fonctionnalité (`dict/fonctionnalites.yml`) ;
- le **cycle d'un lot** : éditer → régénérer → tester → livrer.

## Ce qui s'adapte

- les chapitres thématiques : un projet sans messagerie n'a pas de chapitre « émission » ;
- les axes de la grille 360 — en garder la liste **fermée**, mais la réviser par registre
  (un axe qui ne trouve rien sur trois projets se retire) ;
- les tables du dictionnaire — un projet sans API n'a pas de `routes.yml`, mais garde le
  fichier vide pour que le harnais le voie ;
- le POC : une maquette d'interface n'a de sens que pour un produit à interface. Un service ou
  une bibliothèque remplacent le POC par un **prototype de contrat** (schéma, API, jeu
  d'essai) — le principe reste : *il lit le CDC, il ne le recopie pas*.

## Le POC est l'interface définitive, en mode simulé

Un POC jetable est un écran qu'on réécrit. Le POC **est** l'interface du produit ; ce qui l'en
distingue tient en une **liste fermée** : les données initiales engendrées, une couche `Api`
simulée en mémoire (la même couche fera du HTTP en prod — *on remplace un fichier, et rien
d'autre*), le journal des requêtes, les annotations pédagogiques en **surcouche** (partielles
surchargées, fichier non chargé en prod), les pages CDC. Deux modes de chargement, une seule
base de code ; le harnais vérifie que le mode produit **tourne** sans les fichiers du POC.
L'asynchrone dès le POC : une API simulée synchrone cache le seul problème que le produit aura.

## Wiki

Ces fichiers ne sont pas synchronisés au wiki tant qu'ils sont ici : `pm-wiki-sync` énumère
`docs/*.md` en non récursif. Une fois copiés dans `docs/` du projet ils le sont ; `dict/` reste
un dossier de **sources**, jamais une page.
