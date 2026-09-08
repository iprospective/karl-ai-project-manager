# 1N — Audit de l'existant

Mesures prises le <date> sur <quoi — une configuration, une base, un usage réel>. **Rien de
nominatif** n'est consigné : les correspondants, clients, utilisateurs sont comptés, jamais
nommés.

Ce chapitre n'est pas un audit de configuration : c'est une **source d'exigences**. Ce que
l'existant fait mal en dit autant que ce qu'il fait bien.

## Ce qu'on mesure

| Mesure | Valeur |
|---|---|
| | |

<Toujours : le nombre, le volume, la médiane ET la moyenne (elles divergent souvent d'un
facteur 10), la concentration (quel 1 % porte quelle part), la cardinalité, le débit et son
pic, l'heure réelle de pointe.>

## Ce que l'existant ne peut pas signaler

<Les défauts silencieux : la règle qui n'a jamais rien attrapé, le doublon, la condition
morte. Aucun n'est une faute de l'auteur — ce sont les défauts de l'outil.>

## Le point de sécurité

<Ce que l'existant rend usurpable, et comment le nouveau modèle y répond.>

## Ce que l'existant dit vraiment

<La structure implicite : la hiérarchie de dossiers qui est une taxonomie, le préfixe qui
force un ordre, l'ordre des règles qui encode une priorité. Ce sont les **décisions implicites**
— à rendre explicites.>

## La transposition, élément par élément

| Ce que fait l'existant | Ce qui le remplace | Gain |
|---|---|---|
| | | |

## Ce qui ne se transpose pas, et qu'il faut écrire

<Les besoins de l'existant qui n'ont **aucun équivalent** dans le CDC. Ce sont des exigences
nouvelles.>

## Ce que cet audit ne prouve pas

<Une seule source, un seul usage : dire ce qui reste à mesurer avant d'y appuyer un chiffrage.>

## Méthode

<Comment on a mesuré sans lire les contenus : index, comptages côté serveur, agrégats. Le
coût sur la production. Ce qui rend l'audit reproductible chez un autre client.>
