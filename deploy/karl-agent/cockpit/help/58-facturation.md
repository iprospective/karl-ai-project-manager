# Facturation — valider son temps de travail, une journée à la fois

**💶 facturation** (menu du haut) répond à la question qu'on se pose en fin de mois :
*combien ai-je réellement travaillé ce jour-là, et pour qui ?*

L'écran montre **une journée**. On la relit, on la corrige si besoin, on la **valide** —
et la validation écrit les saisies de temps dans Redmine, pour cette journée seulement.
Jamais un mois en bloc : un mois posé d'un coup ne se relit pas, une journée si.

## Ce que l'écran montre

| Chiffre | Ce que c'est |
|---|---|
| **mesuré** | le temps humain observé dans les traces, plages **fusionnées** — le même moment n'est jamais compté deux fois |
| **déjà noté** | ce qui est déjà dans Redmine ce jour-là ; c'est **déduit** de la proposition |
| **proposé** | ce que la validation ajouterait |
| **IA** | les tours d'agent de la journée, leur durée et leurs tokens |

Sous les chiffres, la **frise** aligne deux voies sur la même échelle : le temps
**humain** (les plages mesurées) et le travail de l'**IA** (un repère par tour). C'est
elle qui justifie une plage — une heure de présence se défend par ce qui s'y est passé.
Le bandeau plus clair, derrière, est la plage d'**heures normales** déclarée.

La frise est **colorée par client** : chaque plage prend la couleur du client qui y
domine, et la notice dessous donne la correspondance avec le cumul de la journée. La
couleur ne dit que le dominant — le **survol** donne la répartition complète d'une plage
(« pisceen 12 min · calicote 4 min »). La **pause** a sa propre bande, hachurée et neutre :
elle ne se facture à personne.

La teinte d'un client est dérivée de son nom : la même partout, d'une journée à l'autre.

## Corriger la journée

La ligne **début / fin / pause** est une *proposition*, déduite des traces et **ramenée
à la plage ouvrée** (8 h – 19 h). C'est volontaire : une dernière trace à 23 h 44 ne doit
pas proposer une journée de 14 h, qui servirait ensuite de plancher. Ce qui a été laissé
dehors est **dit** sous la ligne ; une soirée se rajoute à la main si elle doit compter.

Le **client principal** sert les journées passées chez un client : il dit à qui revient
le temps de la journée quand les traces ne le disent pas seules. Le **lieu**
(présentiel / distanciel) se note à la journée — il conditionne le déplacement.

### La pause de midi

Sous les horaires, l'écran dit ce qu'il en sait : *« pause visible dans les traces :
12:36–13:32 »*, ou *« aucune pause visible ce jour-là »* — en orange dans ce cas.

Elle ne se devine jamais : une journée sans trou à midi peut être une journée sans pause
(sandwich devant l'écran) comme une pause que rien n'a tracée. **+ pause midi** la note en
un clic, à la durée configurée. Rien n'est écrit dans Redmine à ce moment-là : la pause
entre dans la proposition, qui reste à valider.

Sa destination se règle une fois pour toutes dans ton `timesheet.yml` (`<core>/var/users/<toi>/`) :

```yaml
pause:
  client: iprospective
  project_id: 19          # projet Redmine (id numérique)
  activity_id: 27         # activité « Pause »
  commentaire: "repas midi"
  heures: 1.0             # durée proposée en un clic
  plage: ["11:30", "14:30"]
  trou_min: 30            # en deçà, la pause « n'apparaît pas »
```

### Ce qui ne se facture à personne

Un groupe porte la mention **non facturé** quand son entité est de type `self` — dans ton
cas `iprospective` et `lemathou`. Cette liste **ne se déclare pas** ici : elle est déjà
dans les manifestes PM, et la redéclarer serait la voir diverger un jour. Ce temps est
noté dans Redmine comme le reste ; il n'entre simplement dans aucune facture.

### Où ces informations sont enregistrées

Début, fin, pause, client principal, projet et lieu sont **des métadonnées de journée** :
elles ne sont pas dans Redmine, qui ne connaît que des saisies de temps. Elles vivent avec
le reste des données d'exploitation du PM, dans `<core>/var/timesheet/<AAAA-MM>.days.yml`,
et **ne sont écrites que lorsque tu cliques sur Enregistrer** — tant que tu ne l'as pas
fait, ce que l'écran montre est une proposition recalculée depuis les traces à chaque
ouverture.

```yaml
'2026-08-26':
  debut: '09:00'
  fin: '18:00'
  client: matnat
  lieu: presentiel
```

Le même dossier porte le cache des traces, celui des commits et les sauvegardes de reprise.
`var/` est hors git : c'est de l'état, pas du versionné — il suit donc la sauvegarde du core,
pas son historique. Porter ces champs dans Redmine reste une question ouverte : **RM3298**.

Les **réglages** (tes clients, tes absences, tes horaires habituels) sont dans ton dossier de
conf PM : `<core>/var/users/<toi>/timesheet.yml`. Hors git (ils n'ont rien à faire dans un
dépôt partagé) et jamais dans ton home.

**Enregistrer** pose l'ajustement (rien ne part dans Redmine), la journée se recalcule
aussitôt. **↺ ajustement** revient à ce que les traces disent.

## Le temps transversal

Le travail sur le PM, l'infra et les écosystèmes produit (redmine, prestashop, dolibarr)
n'est pas facturable en soi. La ligne « temps transversal » dit ce qu'il en a été fait, et
selon quelle clé :

- **réparti sur les clients travaillés** — en semaine, pendant les heures ouvrées ;
- **à ma charge** — le soir, la nuit, le week-end ;
- **écarté** — une journée sans activité cliente n'a personne à qui l'imputer.

Chaque ligne de la proposition nomme la part d'**outillage PM mutualisé** qu'elle porte.

## Ce qui s'est passé — un seul fil

Sous les boutons, **une** liste chronologique réunit tout ce que la journée a laissé :

| Genre | Ce que c'est |
|---|---|
| **trace** | une trace horodatée : sa source, sa cible, un extrait. Les traces d'agent sont grisées — elles *attribuent* le temps, elles n'en *créent* pas |
| **commit** | ce qui a été produit, tous dépôts confondus, à la minute |
| **pm** | la plomberie PM (`pm(tick)`, moissons, rapports) : elle date l'activité sans la décrire, donc elle est estompée |
| **IA** | un tour d'agent : sa durée, ses tokens |

Trois listes séparées obligeaient à faire la couture dans sa tête pour savoir ce qui
précède quoi. Ici, tout se lit dans l'ordre où c'est arrivé.

### Le temps IA et les tours parallèles

Le chiffre affiché est celui que les tours **déclarent** — il n'est pas raboté. Quand
plusieurs agents tournent en même temps, leurs durées se recouvrent : le travail produit
dépasse alors le temps écoulé, et c'est normal. Le recouvrement est **signalé** (dans le
survol du chiffre, et sur la ligne du tour dans le fil), jamais retranché.

Le **client** et le **projet** se choisissent maintenant dans un menu, alimenté par le
référentiel PM. Changer de client remet le projet à zéro. Une valeur posée autrefois et
absente du référentiel reste proposée : un menu ne fait jamais disparaître une donnée.

## Reprendre une journée

La liste **déjà noté dans Redmine** donne pour chaque saisie son **client** et son
**projet** en deux colonnes, puis le ticket et le commentaire. Le client est résolu depuis
le manifeste PM du projet Redmine ; quand aucun projet PM ne correspond, la colonne client
reste vide et le nom Redmine tient lieu de projet — on n'invente pas un rattachement.

Chaque saisie déjà notée porte son origine : **outil** ou **à la main**. Si tu repères une
incohérence — un volume qui ne colle pas au temps mesuré, un client qui n'a rien à faire là —
le bouton **↺ reprendre** retire les saisies que l'outil a posées ce jour-là, et rien d'autre.

- **Tes saisies à la main ne sont jamais touchées.** La frontière est la marque technique que
  l'outil pose dans ses commentaires ; ce qu'il n'a pas écrit, il ne peut pas l'effacer.
- **Une sauvegarde JSONL est écrite avant la suppression**, dans
  `~/.local/state/mmi-pm/timesheet/reprises/`. Rien n'est perdu.
- La journée est **réanalysée** dans la foulée : les traces sont rejouées, une nouvelle
  proposition apparaît, tu l'ajustes et tu la valides.

Ce geste ne part **jamais tout seul** : ni l'ouverture d'une journée, ni ⟳, ni la validation
ne suppriment quoi que ce soit. Il faut le demander, journée par journée.

En CLI : `mmi-pm timesheet --day <jour> --revoke` (ajouter `--dry-run` pour voir sans supprimer).

## Valider

Le bouton du bas **annonce ce qu'il va écrire** : les clients et le total. La confirmation
reprend le détail. Après l'écriture, la journée est **relue** depuis Redmine — ce qui
s'affiche ensuite est ce qui s'y trouve, pas ce qu'on espérait y avoir mis.

- **simuler** montre le résultat sans rien écrire.
- Une journée dont tout est déjà noté à la main se valide **sans rien ajouter**.
- Une journée validée ne se revalide pas : le bouton s'éteint.

La première ouverture d'une journée rejoue les traces (quelques secondes) ; ensuite elle
est immédiate. **⟳ relire** force le rejeu.

En CLI, la même chose : `mmi-pm timesheet --day 2026-09-18` (relire),
`--start/--end/--client` (ajuster), `--apply` (valider).
