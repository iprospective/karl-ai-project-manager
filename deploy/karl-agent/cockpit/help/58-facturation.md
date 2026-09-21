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

## Corriger la journée

La ligne **début / fin / pause** est une *proposition*, déduite des traces et **ramenée
à la plage ouvrée** (8 h – 19 h). C'est volontaire : une dernière trace à 23 h 44 ne doit
pas proposer une journée de 14 h, qui servirait ensuite de plancher. Ce qui a été laissé
dehors est **dit** sous la ligne ; une soirée se rajoute à la main si elle doit compter.

Le **client principal** sert les journées passées chez un client : il dit à qui revient
le temps de la journée quand les traces ne le disent pas seules.

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
