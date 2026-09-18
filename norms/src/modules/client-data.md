> 📂 **Module `client-data` — quand lire ceci :** j'écris un test, une fixture, un exemple, un template ou une fiche `knowledge/` dans un dépôt publiable (`.client-data-guard.yml` à sa racine) · le hook pre-commit refuse mon commit pour « données client » · je dois ranger une information d'exploitation propre à un client (instance, domaine, version déployée, compte d'accès, contact).
> **Outils :** `pm-check-no-client-data`, `pm-pre-commit` · **Préchargé par :** *(personne — ouvert à la demande via le déclencheur KERNEL, tripwire #21)*.

## Données client — rien dans un dépôt publiable

Ce module détaille le **tripwire #21**.

### Pourquoi

Le dépôt de code PM part sur un **miroir GitHub public**. Pendant 25 jours, il y a exposé
les URL des ERP de production de trois clients **avec leur version exacte** de Dolibarr,
leurs branches de déploiement, un chemin serveur, un compte d'accès chez un hébergeur,
une table de routage mail et des adresses nominatives de contacts (incident RM3200,
2026-09-15). Rien de tout cela n'était un secret au sens du tripwire #11 — aucun token
n'a fui — et c'est précisément pourquoi personne ne l'avait vu : **une URL couplée à
une version précise et à un retard de déploiement documenté est une liste de
vulnérabilités applicables**, servie sur un plateau.

Deux causes, qu'il ne faut pas confondre :

- **aucune règle ne l'interdisait**. Les jeux de test avaient été écrits en recopiant
  les données de travail — le plus court chemin vers un test réaliste ;
- **le miroir a changé la nature de l'existant sans que personne ne le repasse en
  revue**. Ce qui était une négligence interne est devenu une exposition publique le
  jour de sa création.

### Ce qui est interdit dans un dépôt publiable

Tout ce qui nomme un client ou l'une de ses instances :

| Donnée | Exemple de fuite réelle (RM3200, anonymisé) |
|---|---|
| nom ou slug de client, y compris collé (`php_<client>`, `<client>-presta`) | un slug dans une fixture de cockpit |
| domaine ou nom d'hôte, y compris sous un domaine qui ne porte PAS son nom | `erp.<client>.com`, le Gogs d'un client sous son nom commercial |
| IP d'une machine | — |
| chemin serveur | `/home/erp-<client>/public_html` dans un **template** d'aspect, donc recopié dans chaque projet créé |
| version déployée d'une instance | un tableau « instance / version / branche » dans une fiche `knowledge/` |
| compte d'accès | `<client>@srv1.<hebergeur>.com` en exemple de syntaxe dans la référence NORMS |
| nom, prénom, adresse d'un contact | les vraies fiches de l'annuaire, recopiées en fixtures |

Un nom de client en prose — « corrigé chez X » dans un Changelog — reste une mention
commerciale et non une donnée d'exploitation ; il reste **interdit à l'ajout** (le hook
le refuse), mais l'existant est une dette à part, sans urgence.

### Où va quoi

| Ce que c'est | Où ça vit | Pourquoi |
|---|---|---|
| la **méthode** (procédure de MEP, protocole de test, recette) | `knowledge/<produit>/` | publiable, partagée entre clients |
| les **instances** d'un client (URL, hôte, chemin, branche, version) | frontmatter `environments:` du `environments.md` **de son projet** | privé, versionné par le dépôt de données, lu par les scripts |
| la **conf réelle** apprise au fil de l'eau (routage mail, …) | `state_dir` (`var/`), hors git | ni versionnée ni publiée ; `var/` est aussi le seul dossier que `core-lock` laisse écrivable au groupe |
| la **conf d'instance** (URL de forge, de Redmine) | `${VAR}` dans `pm.config.yml`, valeur dans `~/.config/mmi-pm/.env` | le mécanisme existe déjà (`GITLAB_URL`, `REDMINE_URL`) |
| les **contacts** | `contacts_dir`, dépôt de données | cf. note de `contacts_dir` dans `pm.config.yml` |

Une fiche `knowledge/` qui a besoin de l'état du parc **renvoie** vers les
`environments.md` des projets : elle ne le recopie pas. Modèle : `knowledge/dolibarr/mep.md`.

### Le jeu fictif

Exemples, fixtures, templates, docstrings : jamais une donnée réelle, même « juste pour
le test ».

- clients : `clienta`, `clientb`… — **un seul mot, sans tiret** : `client-a` n'est pas
  un identifiant JS valide (`{ client-a: true }` ne compile pas) ;
- domaines : TLD **`.example`** (réservé, RFC 2606 — ne peut jamais exister) ;
  `example.com` pour une adresse chez un webmail ;
- personnes : prénoms et noms génériques (Alice Martin, Bob…) ; vérifier qu'une même
  fixture ne donne pas deux fois le même prénom (collision rencontrée en RM3200).

Trois pièges vus en renommant l'existant, à connaître avant d'écrire un test :

- une valeur **dérivée de la conf réelle** (le slug déduit d'une instance déclarée dans
  `pm.config.yml`) ne se renomme pas dans le test seul — on redéclare l'instance en
  fictif **dans la fixture**, pour que le test ne dépende plus du tout du parc ;
- un renommage **change l'ordre alphabétique** : les attendus d'ordre et d'index sont à
  revoir ;
- un domaine peut être **échappé** dans une regex (`srv\.x\.com`) : un remplacement
  naïf ne le voit pas.

### Le garde-fou — `pm-check-no-client-data`

**Activation par dépôt.** Un dépôt se déclare publiable par un fichier versionné
`.client-data-guard.yml` à sa racine. Sans lui, rien n'est contrôlé : un dépôt de projet
client nomme son client, c'est son objet. Le fichier ne porte **aucune donnée client** :
`exempt` (globs non contrôlés — chaque entrée est un trou, à justifier par un ticket) et
`common_words` (mots courants qui, s'ils sont aussi un slug de client, ne sont signalés
qu'en position d'identifiant).

**Au commit.** `pm-pre-commit` lance le contrôle sur les **lignes ajoutées** de l'index —
une dette existante ne bloque pas chaque commit qui touche le fichier. Une donnée client
⇒ **refus**, avec fichier, ligne et nature.

**Les motifs** ne sont jamais écrits dans le code : ils sont lus à chaque exécution
dans les données privées — entités `type: client` (slug, nom), manifestes et
`environments.md` de leurs projets (hôtes, adresses, IP), annuaire de contacts
(adresses, « prénom nom » des non-internes), table de routage mail. Un produit
(`type: product`), soi-même (`self`), le domaine maison, un webmail grand public et
une plateforme partagée (GitHub, OVH…) ne sont jamais des motifs.

**Limite assumée.** Le garde-fou ne connaît que ce que les données déclarent. Un client
dont le domaine ne porte pas son nom lui échappe tant que ses instances ne sont pas
renseignées — c'est exactement ainsi que le domaine commercial d'un client avait échappé
au premier audit de RM3200. **Renseigner le `environments.md` d'un projet, c'est aussi
armer le garde-fou.**

| Commande | Effet |
|---|---|
| `pm-check-no-client-data` (`--staged`) | lignes ajoutées dans l'index — ce que lance le hook |
| `pm-check-no-client-data --all [--summary]` | audit de tout le versionné (l'existant) |
| `pm-check-no-client-data --history [--summary]` | tout l'historique : chaque version de chaque fichier, supprimés compris, et les messages de commit |
| `pm-check-no-client-data --patterns` | combien de motifs par nature — **jamais les valeurs** : elles sont les données |

Sorties : `0` rien trouvé (ou dépôt non déclaré publiable), `1` donnée client trouvée,
`2` contrôle impossible (données privées injoignables d'ici — rien n'a été vérifié).

**Échappatoires, toutes tracées.**

- marqueur `client-data-guard: allow` sur la ligne : pour une **dette connue et suivie
  par un ticket** (la conf active d'un client dans `pm.config.yml`, en attendant son
  déplacement), jamais pour faire passer un commit ;
- `PM_SKIP_CLIENT_DATA_CHECK=1` : désactive le contrôle, **annoncé à l'écran** ;
- `git commit --no-verify` désactive tous les hooks.

Le hook est **fail-open** comme les autres garde-fous du dépôt : une erreur interne laisse
passer le commit — mais le dit.

### L'existant

Le HEAD du dépôt de code a été nettoyé par RM3200. L'**historique** git garde les
données, et le miroir public les a exposées : leur purge (`git filter-repo
--replace-text`) est un chantier à part, qui réécrit tous les SHA — et donc impose de
recréer chaque clone et chaque worktree.

Avant de rendre un dépôt publiable — nouveau miroir, module rendu public — le passer à
`pm-check-no-client-data --history` : un miroir publie tout ce qu'il reçoit, chaque
version de chaque fichier et chaque message de commit, pas seulement le HEAD.
