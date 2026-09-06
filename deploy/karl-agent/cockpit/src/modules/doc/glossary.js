// models/glossary/glossary — le glossaire du jargon (RM2623/2634 : entrées, index, recherche, soulignage inline
// sûr) et le glossaire d'un PROJET (RM2675 : tableau markdown à 4 colonnes, filtrable). RM2889 : sorti du monolithe.
import { html, raw } from "../../core/html.js";

// Termes du jargon du cockpit. `c` = catégorie (glossGroups) · `a` = alias/pluriels · `inline:false` = panneau
// seulement, jamais souligné dans les textes (mot trop courant/ambigu). Factuel, lisible par un non-développeur.
export const GLOSSARY = [
  // — Git & versionnage —
  { t: "worktree", c: "git", a: ["worktrees"], d: "Copie de travail Git rattachée à une branche. Un même dépôt peut avoir plusieurs worktrees (dossiers) ouverts en parallèle sur des branches différentes, sans se marcher dessus." },
  { t: "branche", c: "git", a: ["branch", "branches"], d: "Ligne de développement parallèle dans Git : on y travaille sans toucher aux autres." },
  { t: "MR", c: "git", a: ["merge request"], d: "Merge Request : demande de fusion d'une branche vers une autre (dev, main), relue avant d'être acceptée." },
  { t: "promote", c: "git", a: ["promotion"], d: "Faire passer un changement de l'intégration (dev) vers la production (main), via une MR." },
  { t: "rebase", c: "git", d: "Rejouer ses commits par-dessus une autre base (ex. la dernière version de dev) pour garder un historique propre." },
  { t: "commit", c: "git", a: ["commits"], inline: false, d: "Enregistrement d'un lot de modifications dans l'historique Git, avec un message." },
  { t: "merge", c: "git", inline: false, d: "Fusionner les changements d'une branche dans une autre." },
  // — Infra & système —
  { t: "daemon", c: "sys", a: ["daemons", "démon"], d: "Programme qui tourne en arrière-plan en permanence, sans interface (ex. un service qui écoute des requêtes)." },
  { t: "systemd", c: "sys", d: "Le gestionnaire de services de Linux : démarre, arrête et surveille les programmes en arrière-plan (services / daemons)." },
  { t: "tmux", c: "sys", d: "Multiplexeur de terminal : garde des terminaux ouverts côté serveur, auxquels on se rattache (attach) et qui survivent à la déconnexion." },
  { t: "PTY", c: "sys", a: ["pseudo-terminal"], d: "Pseudo-terminal : le « faux » terminal par lequel un programme interactif lit le clavier et écrit à l'écran." },
  { t: "socket", c: "sys", a: ["sockets"], d: "Point de connexion (réseau ou local) par lequel deux programmes s'échangent des données." },
  { t: "socat", c: "sys", d: "Utilitaire qui relie deux flux réseau/locaux (ex. exposer un port local sur l'IP du conteneur)." },
  { t: "vhost", c: "sys", a: ["virtual host", "vhosts"], d: "Hôte virtuel : configuration qui fait répondre un serveur web à un nom de domaine donné (ex. karl.lxc)." },
  { t: "reverse proxy", c: "sys", d: "Serveur en façade qui reçoit les requêtes et les redistribue vers les vrais services derrière (routage, HTTPS, cache)." },
  { t: "sidecar", c: "sys", d: "Petit service auxiliaire lancé à côté du principal pour lui rendre un service précis (ex. le moteur de reconnaissance vocale)." },
  { t: "LXC", c: "sys", a: ["conteneur"], d: "Conteneur Linux : un environnement isolé léger (ici le conteneur « dev ») qui partage le noyau de l'hôte." },
  { t: "teardown", c: "sys", a: ["teardowns"], d: "Démontage : arrêt propre et nettoyage d'un environnement de test ou de ressources après usage." },
  { t: "canari", c: "sys", a: ["canary", "canaris"], d: "Sonde ou déploiement témoin lancé en avance pour détecter un problème avant qu'il ne touche tout le monde." },
  { t: "attach", c: "sys", d: "Se rattacher à une session en cours pour en voir — ou en prendre — le terminal en direct." },
  { t: "hook", c: "sys", a: ["hooks"], d: "Point d'accroche : du code déclenché automatiquement sur un événement (ex. après un commit, au démarrage d'une session)." },
  { t: "sandbox", c: "sys", d: "Bac à sable : environnement isolé où exécuter du code sans risque pour le reste." },
  { t: "whitelist", c: "sys", a: ["liste blanche"], d: "Liste d'autorisation : seuls les éléments listés sont permis, le reste est refusé par défaut." },
  { t: "stdout", c: "sys", a: ["stderr"], d: "Sortie standard d'un programme (le texte normal qu'il affiche) ; stderr est la sortie d'erreur." },
  { t: "stdin", c: "sys", d: "Entrée standard : le canal par lequel un programme reçoit du texte en entrée (au clavier ou d'un autre programme)." },
  { t: "process", c: "sys", a: ["processus"], inline: false, d: "Programme en cours d'exécution vu par le système, avec sa propre mémoire." },
  { t: "thread", c: "sys", a: ["threads"], inline: false, d: "Fil d'exécution à l'intérieur d'un process : plusieurs threads travaillent en parallèle en partageant la mémoire." },
  { t: "cache", c: "sys", inline: false, d: "Réserve de résultats déjà calculés/chargés pour répondre plus vite sans refaire le travail." },
  { t: "ownership", c: "sys", a: ["propriété", "owner"], d: "Propriété d'un fichier ou dossier au sens système : quel utilisateur et quel groupe le possèdent. Avec les permissions, c'est ce qui détermine qui peut le lire, l'écrire ou le supprimer (ex. « root:pm » = possédé par root, groupe pm)." },
  { t: "enforce", c: "sys", a: ["enforcement", "appliquer"], d: "Faire respecter une règle automatiquement et de façon répétable — un outil qui remet en conformité à chaque passage (ex. les permissions d'un dossier) plutôt que compter sur une action manuelle, qui dérive avec le temps." },
  // — Web & interface —
  { t: "HTTPS", c: "web", a: ["secure context", "contexte sécurisé"], d: "Version chiffrée de HTTP : la connexion au site est protégée ; requise pour certaines fonctions (micro, presse-papier)." },
  { t: "endpoint", c: "web", a: ["endpoints", "route", "routes"], d: "Point d'entrée d'une API : une URL/route qui répond à une requête (ex. /health)." },
  { t: "SPA", c: "web", a: ["single page application"], d: "Single Page Application : une appli web qui tient dans une seule page et met à jour l'affichage sans la recharger (le cockpit en est une)." },
  { t: "DOM", c: "web", d: "La représentation en mémoire de la page (ses éléments) que le code manipule pour changer l'affichage." },
  { t: "regex", c: "web", a: ["expression régulière", "regexp"], d: "Expression régulière : un motif qui décrit un texte à rechercher/valider (ex. « RM suivi de chiffres »)." },
  { t: "toast", c: "web", a: ["toasts"], d: "Petite notification éphémère qui apparaît puis disparaît (confirmation, erreur)." },
  { t: "pill", c: "web", a: ["pills", "chip"], d: "Petite étiquette arrondie cliquable dans l'interface (un badge compact)." },
  { t: "overlay", c: "web", d: "Surcouche affichée par-dessus l'interface (fenêtre modale, panneau flottant)." },
  { t: "poll", c: "web", a: ["polling"], d: "Interroger régulièrement une source pour voir si quelque chose a changé (ex. le cockpit demande l'état des sessions toutes les X secondes)." },
  // — IA & tokens —
  { t: "token", c: "ia", a: ["tokens"], d: "Unité de découpage du texte pour un modèle d'IA (~¾ d'un mot). La consommation et le coût se comptent en tokens." },
  { t: "LLM", c: "ia", a: ["grand modèle de langage"], d: "Large Language Model : un grand modèle de langage (ex. Claude), entraîné pour comprendre et générer du texte." },
  { t: "prompt", c: "ia", a: ["prompts"], d: "Le texte d'instruction envoyé au modèle pour lui dire quoi faire." },
  { t: "thinking", c: "ia", d: "Mode où le modèle « réfléchit » (raisonne) avant de répondre — plus lent mais plus fiable sur les tâches difficiles." },
  { t: "contexte", c: "ia", a: ["fenêtre de contexte", "context window"], inline: false, d: "La fenêtre de contexte : la quantité maximale de tokens (historique + réponse) qu'un modèle peut traiter en une fois." },
  { t: "débit", c: "ia", a: ["throughput"], inline: false, d: "Vitesse de production : ici tokens par minute et coût par heure d'une session." },
  { t: "transcript", c: "ia", a: ["transcripts"], d: "Enregistrement complet des échanges d'une session (messages, outils appelés), relu pour l'affichage et les métriques." },
  { t: "classifieur", c: "ia", a: ["classifier", "classifieurs"], d: "Composant qui range automatiquement une entrée dans une catégorie (ex. décider si un message attend une réponse)." },
  // — PM / NORMS —
  { t: "worklog", c: "pm", a: ["worklogs"], d: "Journal d'avancement d'une session : la liste des tickets touchés et leur état, tenu à jour au fil de l'eau." },
  { t: "backlog", c: "pm", d: "File d'attente des tâches à faire, pas encore prises en charge." },
  { t: "MEP", c: "pm", d: "Mise En Production : déployer le code validé pour qu'il tourne en conditions réelles." },
  { t: "serve-check", c: "pm", a: ["servecheck"], d: "Vérification rapide qu'une page se sert bien (réponse HTTP 200) avant de conclure qu'une mise en prod fonctionne." },
  { t: "frontmatter", c: "pm", d: "Bloc de métadonnées en tête d'un fichier (souvent en YAML, entre ---), séparé du corps (ex. le statut d'un ticket)." },
  { t: "worker", c: "pm", a: ["workers"], d: "Agent exécutant : celui qui traite concrètement une tâche, par opposition à l'orchestrateur qui répartit." },
  { t: "orchestrateur", c: "pm", a: ["orchestrateurs", "orchestration"], d: "Celui qui répartit et coordonne le travail entre les workers (agents exécutants), sans le faire lui-même." },
  { t: "NORMS", c: "pm", d: "Le corps de règles du système PM (protocole worker, statuts, git) que les agents doivent suivre." },
  { t: "KERNEL", c: "pm", a: ["kernel"], d: "Le « noyau » des normes : le document obligatoire listant déclencheurs et garde-fous, à lire avant d'ouvrir les modules détaillés." },
  { t: "onboarding", c: "pm", a: ["prise de contexte", "mise en contexte"], d: "Mise en contexte d'un agent AVANT qu'il agisse : il lit les règles (KERNEL, puis son rôle), puis la fiche du client, du projet et de la tâche. Sans cette étape, l'agent suppose au lieu de savoir." },
  { t: "tripwire", c: "pm", a: ["tripwires", "garde-fou"], d: "Garde-fou : une règle qui se déclenche pour empêcher une erreur (ex. interdire un push direct sur main). Ce qui l'applique concrètement dans un outil s'appelle une garde." },
  // `inline: false` : « garde » est aussi un mot français ordinaire (« il garde
  // son statut ») — le souligner partout produirait surtout des faux positifs.
  // Il reste cherchable dans le glossaire, il n'est simplement pas surligné.
  { t: "garde", c: "pm", a: ["gardes"], inline: false, d: "Vérification posée dans le code, qui refuse une opération tant que ses conditions ne sont pas réunies (ex. refuser d'écrire sur un ticket d'un autre projet sans --cross-project). Le tripwire est la règle ; la garde est le cran d'arrêt qui la fait respecter." },
  { t: "optimistic locking", c: "pm", a: ["verrouillage optimiste"], d: "Verrouillage optimiste : avant d'écrire, on vérifie que personne n'a modifié la donnée entre-temps (via un champ de version)." },
  { t: "porcelain", c: "pm", d: "Mode « machine » d'une commande : sortie stable et simple à lire par un script (ex. juste l'identifiant)." },
  { t: "CF", c: "pm", inline: false, d: "Custom Field : un champ personnalisé d'un ticket Redmine (ex. « protocole de test »)." },
  { t: "a_mep", c: "pm", a: ["a mep"], d: "Statut d'un ticket : « à mettre en production » — développé et validé, en attente de déploiement." },
  { t: "PM", c: "pm", inline: false, d: "Project Management : le système de gestion de projet iProspective (tickets, normes, agents)." },
  { t: "cascade", c: "pm", inline: false, d: "Héritage client → projet → tâche : une valeur définie en haut s'applique en dessous, sauf si on la redéfinit." },
  { t: "ferme", c: "pm", inline: false, d: "Statut d'un ticket : clôturé (terminé)." },
  { t: "tick", c: "pm", a: ["ticks"], d: "Battement périodique : une itération régulière d'un traitement (ex. un relevé de métriques à intervalle fixe)." },
  // — Général —
  { t: "clobber", c: "gen", d: "Écraser des données existantes sans le vouloir (un fichier, une version) — en général une erreur à éviter." },
  { t: "writer", c: "gen", a: ["writers"], d: "Composant qui écrit (dans un fichier, une base…), par opposition au lecteur (reader)." },
  { t: "ack", c: "gen", d: "Accusé de réception (« acknowledge ») : confirmation qu'un message ou un événement a bien été reçu et pris en compte." },
  { t: "idempotent", c: "gen", d: "Se dit d'une opération qu'on peut rejouer plusieurs fois sans changer le résultat au-delà de la première." },
  { t: "one-off", c: "gen", a: ["one off", "one-offs"], d: "Action faite une seule fois, à la main, parce que l'outil qui devrait la porter n'existe pas encore (ex. créer un dépôt sans script dédié). Assumée et tracée, elle dépanne ; répétée, elle signale qu'il manque un outil." },
  { t: "scope", c: "gen", inline: false, d: "Périmètre : ce qui est concerné ou couvert (par une variable, un changement, une tâche)." },
  { t: "session", c: "gen", a: ["sessions"], inline: false, d: "Une conversation/instance de travail d'un agent (Claude Code…), suivie individuellement." },
];

// glossNorm : clé canonique d'un terme (minuscule,
// espaces réduits, ponctuation de bord retirée).
export function glossNorm(term) {
  return String(term == null ? "" : term).toLowerCase().trim()
    .replace(/\s+/g, " ")
    .replace(/^[^0-9a-zà-ÿ-]+|[^0-9a-zà-ÿ-]+$/g, "");
}

// buildGloss : indexe le glossaire.
// Retourne { map, surfaces } : map[cléNormalisée] = {t,d} pour terme ET alias ;
// surfaces = libellés à repérer inline (entrées inline uniquement), triés du
// plus long au plus court pour un « longest match » dans l'alternance regex.
export function buildGloss(entries) {
  const map = {}, surf = [];
  for (const e of (entries || [])) {
    const labels = [e.t].concat(e.a || []);
    for (const l of labels) {
      const k = glossNorm(l);
      if (k && !map[k]) map[k] = { t: e.t, d: e.d };
    }
    if (e.inline !== false) { for (const l of labels) surf.push(l); }
  }
  surf.sort((x, y) => y.length - x.length);
  return { map: map, surfaces: surf };
}

// glossMatch : entrées filtrées par requête (sur le
// terme, ses alias ou sa définition), triées alpha sur le terme.
export function glossMatch(query, entries) {
  const q = String(query || "").toLowerCase().trim();
  const list = (entries || []).filter(function (e) {
    if (!q) return true;
    if (String(e.t).toLowerCase().indexOf(q) >= 0) return true;
    if ((e.a || []).some(function (a) { return String(a).toLowerCase().indexOf(q) >= 0; })) return true;
    return String(e.d).toLowerCase().indexOf(q) >= 0;
  });
  return list.slice().sort(function (x, y) { return String(x.t).localeCompare(String(y.t)); });
}

// glossGroups : regroupe les entrées par catégorie,
// dans un ordre fixe, chaque groupe trié alpha. Entrée sans `c` → « gen ».
// Catégorie inconnue → rejetée en fin de liste (sécurité), jamais perdue.
export function glossGroups(entries) {
  const ORDER = [
    ["git", "Git & versionnage"], ["sys", "Infra & système"],
    ["web", "Web & interface"], ["ia", "IA & tokens"],
    ["pm", "PM / NORMS"], ["gen", "Général"],
  ];
  const by = {};
  for (const e of (entries || [])) {
    const c = e.c || "gen";
    (by[c] = by[c] || []).push(e);
  }
  const alpha = function (x, y) { return String(x.t).localeCompare(String(y.t)); };
  const out = [];
  for (const pair of ORDER) {
    const arr = by[pair[0]];
    if (arr && arr.length) out.push({ cat: pair[0], label: pair[1], items: arr.slice().sort(alpha) });
  }
  const known = ORDER.map(function (p) { return p[0]; });
  for (const c in by) {
    if (known.indexOf(c) < 0) out.push({ cat: c, label: c, items: by[c].slice().sort(alpha) });
  }
  return out;
}

// glossify : dans un texte DÉJÀ échappé (aucune balise
// HTML), enveloppe les termes connus dans <span class="gloss" data-term=…>.
// Match uniquement sur frontières de mot ; `built` injectable pour les tests.
export function glossify(escaped, built) {
  const s = String(escaped == null ? "" : escaped);
  built = built || GLOSS;
  if (!built || !built.surfaces.length) return s;
  const alt = built.surfaces.map(function (x) {
    return x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }).join("|");
  const re = new RegExp("\\b(" + alt + ")\\b", "gi");
  return s.replace(re, function (m) {
    const hit = built.map[glossNorm(m)];
    if (!hit) return m;
    return String(html`<span class="gloss" data-term="${glossNorm(hit.t)}" title="${hit.d}">${raw(m)}</span>`);
  });
}

/** L'index prêt à l'emploi du glossaire du cockpit. */
export const GLOSS = buildGloss(GLOSSARY);

// — glossaire de projet (RM2675) : docs/glossaire.md, écrit par pm-glossaire.py —
export function glossaireRows(md) {
  const out = [];
  for (const raw of String(md || "").split("\n")) {
    const l = raw.trim();
    if (!l.startsWith("|") || l.startsWith("|---") || /^\|\s*Terme\s*\|/i.test(l)) continue;
    const c = l.replace(/^\||\|$/g, "").split("|").map(x => x.trim());
    if (!c.length || !c[0]) continue;
    while (c.length < 4) c.push("");
    out.push({ terme: c[0], definition: c[1], contexte: c[2], alias: c[3] });
  }
  return out;
}

export function glossaireFiltre(rows, q) {
  const s = String(q || "").trim().toLowerCase();
  if (!s) return rows || [];
  return (rows || []).filter(r =>
    (r.terme + " " + r.definition + " " + r.contexte + " " + r.alias).toLowerCase().includes(s));
}
