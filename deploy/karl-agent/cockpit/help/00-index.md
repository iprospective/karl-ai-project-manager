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
| 📧 **emails** | courrier de karl → tickets (relève, routage, rédaction) | [Emails](emails) |
| ⚙ **commandes pm** | catalogue des actions PM en un clic | [Commandes & actions](commandes) |
| 🔧 **réglages** | thème, appareils, dictée, plafond mémoire, conf PM | [Réglages](reglages) |

Le panneau **central** garde tes vues en [onglets](onglets) : une vue ouverte est un
onglet temporaire, épingle-la pour la conserver.

La colonne de droite affiche la session attachée : terminal, worklog, état.

## Les boutons d'aide

- **🔓 déverrouiller** (en-tête) n'apparaît que si le coffre de secrets ou l'agent
  SSH est fermé — voir [Verrous](verrous).
- **❓ aide** (en-tête) ouvre cette documentation.
- Un **`?`** près d'un panneau ouvre directement la page qui le concerne.

Les pages d'aide sont des fichiers markdown versionnés dans le repo
(`deploy/karl-agent/cockpit/help/`), servis par karl-agent. Elles sont
maintenues **au fil des développements** (norme « Développement du PM »).
