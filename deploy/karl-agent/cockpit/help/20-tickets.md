# Tickets

Le panneau **🎫 tickets** recherche et ouvre les tickets du PM (fichiers
markdown structurés, synchronisés avec Redmine).

## Tickets ouverts (la carte du haut)

Chaque ticket consulté s'empile dans **Tickets ouverts**, groupé par projet et
trié par urgence de statut — de quoi revenir à ce qu'on avait sous la main.

La carte est **repliée au départ** et s'ouvre d'un clic sur son en-tête : la
liste monte jusqu'à 40 lignes et repousserait sinon la recherche et la création
hors de l'écran. Le nombre entre parenthèses dit ce qu'elle contient sans avoir
à l'ouvrir (`(vide)` quand il n'y a rien).

Ton choix est mémorisé **par navigateur** : laissée ouverte, elle se rouvrira au
prochain chargement. `✕ vider` remet la liste à zéro.

## Rechercher — local, Redmine, ou les deux

Sous le champ de recherche, quatre sélecteurs :

- **Source.** `📁 local` (défaut) cherche dans les fichiers de tickets du PM.
  `🌐 Redmine` interroge le tracker : c'est le seul moyen de trouver un ticket
  **jamais fetché**, qui n'a donc aucun fichier local. `📁+🌐 les deux` fusionne,
  sans doublon.
- **Client**, **projet**, **statut.** Ils portent sur les deux sources. La liste
  des projets suit le client choisi. Un filtre explicite l'emporte sur le
  contexte client global : c'est le dernier choix fait qui vaut.

Un résultat que le local ignore est marqué **« ⚠ pas en local »**, avec son projet
Redmine et son assignation. Cliquer dessus ouvre le ticket **dans Redmine** : il
n'a ni fichier ni branche, il n'y a rien à lancer ici. Pour le rapatrier :
`redmine-fetch-task.py --issue <id>`.

Si Redmine est injoignable (réseau, identifiants), les résultats **locaux restent
affichés** et l'erreur s'écrit au-dessus. Une API en rade ne doit pas faire croire
qu'un ticket a disparu.

## Ouvrir une fiche

Clique un ticket pour sa **fiche** : titre, statut, description, dernière
activité, protocole de test, branche/MR, environnements, liens (dépend de /
bloque / lié), métriques (tokens, coût, temps).

- Le **titre** d'un ticket est cliquable partout où il apparaît → ouvre la fiche.
- Un lien **↗ Redmine** (`…/issues/<id>`) pointe vers le ticket dans le tracker.

## Sessions du ticket

La section **Sessions** de la fiche dit **qui travaille dessus**, avec la source
de l'information :

- **ancrage** — la session porte l'id du ticket (`karl-RM<id>`) ;
- **registre** — la session a la branche `<id>-…` ou le worktree `…-rm<id>` ;
- **worklog** — la session a ouvert le ticket dans son worklog. C'est la seule
  source pour une session lancée sur un slug, qui traite plusieurs tickets sans
  qu'aucune branche ne porte leur numéro.

Une session vivante s'ouvre d'un clic (**⇱ ouvrir**). Une session éteinte reste
affichée : « a été traité ici, mais plus rien ne tourne » n'est pas « personne ne
s'en occupe ».

Deux façons de lancer le travail depuis la fiche :

- **▶ nouvelle session** — lance `karl-RM<id>` avec le moteur et le modèle
  sélectionnés dans le lanceur (panneau 🖥 sessions). La confirmation les
  rappelle, ainsi que le répertoire et la consigne envoyée. Le bouton est
  désactivé quand la session du ticket tourne déjà : il n'y en a qu'une par
  ticket, ouvre-la.
- **➜ envoyer dans cette session** — pousse « traite la tâche RM<id> » dans une
  session **déjà ouverte**, choisie dans la liste. Les sessions du **projet du
  ticket** viennent en tête ; les autres annoncent leur client/projet, et la
  confirmation le répète — envoyer un ticket dans une session qui travaille
  ailleurs reste possible, mais jamais par inadvertance.

## La fiche dans la colonne de droite

L'onglet **tickets** de la colonne de droite montre le ticket courant en
facettes : **détail** (identité, projet, environnements, git, relations),
**description**, **historique**, **conso** et **workspace**.

La description et l'historique ont leur propre facette, **pleine hauteur** : ils
vivaient auparavant en bas du détail, bridés à une dizaine de lignes chacun,
après plusieurs blocs qu'il fallait faire défiler.

L'**historique** est le journal du ticket, structuré : une entrée par événement,
son horodatage à gauche, son titre, puis son corps rendu. **La plus récente en
tête** — on l'ouvre pour savoir ce qui vient de se passer, pas pour relire le
début.

## Les actions, en bas de la fiche

Un seul bloc **Actions**, filtré par le statut du ticket :

- les **verdicts** (fermer, demander la MEP, renvoyer en correction) n'apparaissent
  que sur un ticket **livré** — en test ou en attente de MEP. Un verdict porte sur
  du travail livré ; le proposer sur un ticket en cours invite à fermer ce qui n'a
  pas été fait. Sur un ticket déjà `a_mep`, « demander la MEP » disparaît : elle
  est déjà demandée ;
- les **actions PM** (passer en cours, commenter, mettre à jour la description…)
  s'adressent à une session : elles restent grisées tant qu'aucune ne peut les
  recevoir, et la ligne du dessous dit laquelle serait visée.

## Cycle de vie (statuts NORMS)

Un ticket suit un flux : `nouveau` → `en_cours` → `a_tester_dev` /
`a_tester_demandeur` → `a_mep` → `ferme`. Les transitions synchronisent Redmine
et journalisent dans le `.log.md` du ticket.

La prise en charge (`en_cours`) implique l'auto-assignation. Les changements de
statut se font via les [commandes PM](commandes) ou la [file de test](tests).
