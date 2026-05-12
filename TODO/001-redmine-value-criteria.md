# TODO 001 — Critères de valeur Redmine à préserver dans toute évolution

| | |
|---|---|
| **Statut** | `pending` |
| **Priorité** | `#priority:normal` |
| **Tags** | `#constraint` `#redmine` `#user-request` `#meta` |
| **Origine** | Demande user — 2026-05-11 (depuis le projet `/zfs/workspaces/infra`) |
| **Créé** | 2026-05-11 |

## Contexte

Lors d'une session sur le projet `infra`, le user a précisé pourquoi Redmine reste
un outil important pour lui aujourd'hui — au-delà de ce qui apparaît dans ce système
de gestion (où Redmine sert d'ID de ticket via `RM{id}` mais où l'essentiel se passe
en Markdown).

Cette précision a une portée **architecturale** : toute évolution future du système
(v2, v3, patterns AI-natifs évoqués dans [`PISTES.md`](../PISTES.md), etc.) doit
**préserver ces trois valeurs** ou les substituer par une alternative au moins
équivalente. C'est une contrainte de design, pas une simple piste.

## Les 3 valeurs concrètes que Redmine apporte au user

1. **Collaboration humaine**
   Redmine est l'outil où les contributeurs humains (équipe, prestataires) suivent
   les tickets, commentent, s'assignent du travail. Le système Markdown ne remplace
   pas un tracker quand plusieurs humains sont impliqués.

2. **Base documentaire avec recherche depuis une UI web**
   Le user peut chercher des contenus historiques (tickets, descriptions, commentaires,
   fichiers attachés) depuis n'importe quel navigateur sans avoir à cloner un repo
   ou ouvrir un IDE.

3. **Communication avec les clients**
   Pour la **majorité** des projets du user, Redmine est l'interface où les clients
   peuvent voir l'avancement, demander des évolutions, suivre les tickets.
   C'est l'outil de relation client externe.

## Implications pour les évolutions du système

Quand on travaille sur les pistes de [`PISTES.md`](../PISTES.md) (notamment celles qui
suggèrent de réduire le rôle de Redmine, ou de basculer sur des patterns AI-natifs),
**vérifier explicitement** :

- [ ] L'évolution proposée préserve-t-elle la collaboration multi-humains ?
      Si non, comment ?
- [ ] L'évolution préserve-t-elle la recherche web sans IDE ?
      Si non, propose-t-elle une UI alternative (dashboard, instance Markdown
      indexée + UI web, etc.) ?
- [ ] L'évolution préserve-t-elle l'interface client externe ?
      Si non, le client doit-il avoir un autre point d'accès ? Ou la majorité
      des projets concernés doivent rester sur le legacy ?

## Notes / pistes (non engageantes)

- Une UI web qui lit/indexe les fichiers Markdown du repo (genre Outline, BookStack,
  Logseq publié, ou un static site generator avec recherche fulltext) pourrait
  couvrir le critère "recherche web" et "collaboration en lecture" — mais pas
  l'écriture multi-utilisateurs.
- Une UI client séparée (portail simple lisant les statuts des tâches Markdown)
  pourrait couvrir le critère "communication client" sans devoir garder Redmine.
- Reste à voir si l'effort de maintenance d'alternatives est inférieur à celui
  de continuer avec Redmine — probablement pas à court terme.

## Critères d'acceptation

Cette TODO est "réalisée" quand :
- Soit toute évolution majeure du système intègre explicitement ces 3 critères dans
  son analyse d'impact (la TODO devient un checklist permanent → on la garde en
  référence sans la fermer).
- Soit on décide qu'elle est obsolète (ex : on passe full Redmine et le système
  Markdown disparaît, ou inverse).

→ Pour l'instant : **garder ouverte indéfiniment**, c'est un garde-fou de design.

## Journal

- **2026-05-11** : TODO créée. Origine : remarque du user pendant une session sur le projet `/zfs/workspaces/infra`, où on discutait de la mise en place du système TODO. Le user a précisé "on verra plus tard pour Redmine" tout en explicitant la valeur qu'il y trouve — d'où cette capture comme contrainte.
