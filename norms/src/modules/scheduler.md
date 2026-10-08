> 📂 **Module `scheduler` — quand lire ceci :** je veux qu'un travail tourne périodiquement · j'allais écrire une ligne de crontab · un job périodique n'a pas tourné, ou tourne mal · je veux savoir ce qui tourne en tâche de fond sur l'instance.
> **Outils :** `pm-scheduler list|history|check|run`, `jobs.reference.yml` · **Préchargé par :** *(personne — ouvert à la demande)*.

# Travaux périodiques — l'ordonnanceur unique

## La règle

**Un travail périodique se déclare dans `jobs.reference.yml`. On n'ajoute pas de ligne
de crontab.** L'instance n'a qu'un seul cron, qui appelle l'ordonnanceur toutes les
5 minutes ; c'est lui qui évalue ce qui est dû.

```
*/5 * * * * python3 "$PM_DIR/scripts/pm-scheduler.py" run >> "$LOG_DIR/scheduler.log" 2>&1
```

Ce n'est pas une préférence de rangement. Un cron nu ne sait rien faire de ce dont ces
travaux ont besoin :

- **il ne garde pas d'état.** « C'est passé quand, et ça s'est bien passé ? » n'avait de
  réponse qu'en fouillant des journaux séparés — quand ils existaient ;
- **il ne verrouille rien.** Cron relance un job même si le précédent tourne encore :
  deux orchestrateurs concurrents s'assignent les mêmes tâches ;
- **il n'inventorie rien.** Avant RM2792, la moitié des jobs PM n'étaient installés
  nulle part : seulement décrits dans `cron.example.sh`, un fichier que personne ne relit.

Un cron ajouté à côté de l'ordonnanceur annule les trois. Si un besoin ne rentre pas
dans le registre, c'est le registre qu'on étend.

## Déclarer un job

```yaml
jobs:
  mon-job:
    schedule: "0 7 * * *"        # cron 5 champs
    command: ["python3", "scripts/mon-outil.py", "--apply"]
    description: >
      Ce que ça fait, et ce qu'on perd si ça ne tourne pas.
```

`command` (liste argv, sans shell) ou `shell` (ligne passée à `bash -c`, avec `pm.env`
et `.env` déjà sourcés) — **exactement un des deux**. Optionnels : `enabled` (défaut
`true` ; à `false`, préciser le motif en commentaire), `timeout` (défaut 900 s), `cwd`.

`pm-scheduler check` valide le registre ; un registre invalide **ne lance aucun job**
plutôt que de lancer ceux qui passent — une erreur de frappe dans une expression cron
ne doit pas se traduire par « la moitié des travaux ont tourné ».

## Trois comportements à connaître

- **Un job jamais vu est ARMÉ, pas exécuté.** À sa première rencontre il est inscrit à
  l'état avec l'instant courant pour repère, et attend sa prochaine occurrence. Sans
  cela, ajouter un job quotidien au registre à 15 h le ferait partir aussitôt, au titre
  de l'occurrence de 6 h déjà passée.
- **Pas de rattrapage en cascade.** Machine éteinte trois jours ⇒ un job quotidien
  tourne **une** fois, pas trois. Rejouer trois fois un résumé quotidien ne rend pas
  trois jours de travail, ça fait trois fois du bruit.
- **Pas de recouvrement.** Un job encore en cours n'est pas relancé : il est tracé
  « déjà en cours ». Un job qui échoue ou qui dépasse son `timeout` n'empêche jamais les
  autres de tourner ; le passage sort en code ≠ 0 pour que l'échec reste visible.

## Un seuil qui dérive : notifier, pas ticketer (RM3177)

Un **état qui dérive** — budget de contexte, invariant du doctor, test rouge durable — se
**notifie** au fil (`pm_notify.add`, RM2792). Il ne produit pas de ticket. Seule une
**action décidée** se ticket (« dégraisser `git-mep.md` », « relever le plafond à N parce
que… »).

Pourquoi c'est une règle et pas un conseil : le budget de précharge NORMS a produit **trois
tickets** pour le même seuil (RM2974, RM2756, RM3035) pendant que la mesure passait de
91,4 % à 96,7 % sans que personne soit alerté au bon moment. Un ticket ne se relit pas, il
attend qu'on aille le chercher. Et un test rouge en permanence cesse d'être un signal : il
devient du décor.

Une veille bien faite tient en quatre points — `pm-context-budget --notify` est l'exemple :

1. **Un job du registre**, pas un cron : la mesure tourne seule.
2. **Des paliers** (info / warn / critical), pas un seul seuil : la marge sert à prévenir
   AVANT de constater.
3. **Un message STABLE, les chiffres en champs.** Sinon chaque mesure écrit une entrée neuve
   et l'anti-répétition du fil tombe : une dérive qui dure doit faire UNE entrée qui remonte.
4. **La tendance, pas seulement la valeur.** « 98 % » ne distingue pas un plateau d'une
   dérive ; « +5,3 pts en 21 j » dit ce qu'il faut faire.

Le gate BLOQUANT (test, doctor en CI) reste en place : la veille ne le remplace pas, elle
fait savoir qu'il est rouge entre deux modifications.

## Regarder ce qui tourne

```bash
pm-scheduler.py list                    # registre + dernier passage + prochain dû + échecs d'affilée
pm-scheduler.py history --job <id>      # les dernières exécutions
pm-scheduler.py run --only <id> --force --dry-run   # ce que ferait ce job
```

État et traces vivent sous `var/scheduler/` (hors arbre tracké) : `state.json`,
`history.jsonl` (2 000 dernières exécutions), et `log/<id>.log` pour la sortie complète.

**`consecutive_failures` est le signal qui compte.** Un job qui échoue une fois est un
incident ; un job qui échoue vingt fois de suite est un job que plus personne ne
surveille — c'est ce compteur qu'une alerte doit lire, pas le dernier code retour.
