# Aide du cockpit

Le **cockpit karl-agent** supervise les sessions d'agents IA, pilote le système
de gestion de projet (PM) et porte la console de test/revue des tickets livrés.

## Se repérer

La colonne de gauche a un onglet par surface :

| Onglet | À quoi ça sert | Aide |
|---|---|---|
| ▶ **en cours** | sessions ouvertes, celles qui attendent une réponse | [Sessions & terminal](sessions) |
| 🎫 **tickets** | rechercher/ouvrir un ticket, lien Redmine | [Tickets](tickets) |
| 🚀 **sessions** | jeux de sessions enregistrés (relancer, autostart) | [Sessions & terminal](sessions) |
| 🧪 **à tester** | file de test/revue des tickets livrés | [À tester & revue](tests) |
| ⚙ **commandes pm** | catalogue des actions PM en un clic | [Commandes & actions](commandes) |
| 🔧 **réglages** | thème, appareils, dictée, plafond mémoire, conf PM | [Réglages](reglages) |

La colonne de droite affiche la session attachée : terminal, worklog, état.

## Les boutons d'aide

- **❓ aide** (en-tête) ouvre cette documentation.
- Un **`?`** près d'un panneau ouvre directement la page qui le concerne.

Les pages d'aide sont des fichiers markdown versionnés dans le repo
(`deploy/karl-agent/cockpit/help/`), servis par karl-agent. Elles sont
maintenues **au fil des développements** (norme « Développement du PM »).
