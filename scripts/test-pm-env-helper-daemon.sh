#!/bin/bash
# Tests des GARDE-FOUS des verbes daemon-* du helper privilégié (RM2693).
#
# Le helper tourne en root via sudo NOPASSWD : sa sécurité est sa seule protection.
# On teste donc ce qu'il REFUSE, pas ce qu'il accepte — un helper qui accepte trop
# est un trou, un helper qui refuse trop n'est qu'une gêne.
set -uo pipefail
H="$(cd "$(dirname "$0")/.." && pwd)/tools/env-runtime/pm-env-helper.sh"
fails=0
ok()  { echo "✓ $1"; }
ko()  { echo "✗ $1"; fails=$((fails+1)); }
chk() { if eval "$2"; then ok "$1"; else ko "$1"; fi; }

# Les validateurs, extraits du helper (ils n'ont pas besoin de root).
eval "$(sed -n '/^vname_ok()/p;/^port_ok()/p;/^arg_ok()/p' "$H")"
PORT_MIN=21000; PORT_MAX=21999

echo "── noms d'env acceptés / refusés ──"
chk "calymix-rm2264 accepté"        'vname_ok calymix-rm2264'
chk "calymix-rm2264-s68 accepté"    'vname_ok calymix-rm2264-s68'
chk "calymix-dev accepté"           'vname_ok calymix-dev'
chk "un nom quelconque REFUSÉ"      '! vname_ok apache2'
chk "une traversée REFUSÉE"         '! vname_ok ../../etc/passwd'

echo "── ports ──"
chk "21000 accepté"                 'port_ok 21000'
chk "80 REFUSÉ (hors plage)"        '! port_ok 80'
chk "22 REFUSÉ"                     '! port_ok 22'
chk "non numérique REFUSÉ"          '! port_ok 21000x'

echo "── arguments d'ExecStart ──"
# Appels DIRECTS (pas d'eval) : ces arguments contiennent justement les caractères
# dont on teste le refus, les passer par une chaîne évaluée les mangerait.
if arg_ok "--port=21000"; then ok "argument ordinaire accepté"; else ko "argument ordinaire accepté"; fi
if arg_ok "$(printf 'a\nUser=root')"; then
  ko "saut de ligne REFUSÉ (injecterait une directive dans l unité)"
else ok "saut de ligne REFUSÉ (injecterait une directive dans l unité)"; fi
if arg_ok '%h/evil'; then ko "%% REFUSÉ (spécificateur systemd)"
else ok "%% REFUSÉ (spécificateur systemd)"; fi

echo "── ce que le SOURCE doit garantir (lecture du helper) ──"
chk "user forcé à l invocateur"     'grep -q "user\" = \"\$SUDO_USER" "$H"'
chk "root explicitement refusé"     'grep -q "refus de lancer un daemon en root" "$H"'
chk "exécutable confiné au workdir" 'grep -q "exécutable hors du workdir" "$H"'
chk "workdir confiné à WS_ROOT"     'grep -q "workdir hors de" "$H"'
chk "marqueur exigé avant suppression" 'grep -q "n.est pas géré par pm-env-helper — refus" "$H"'
chk "unité durcie"                  'grep -q "NoNewPrivileges=true" "$H" && grep -q "ProtectSystem=full" "$H"'
chk "mutations auditées"            'grep -q "audit \"daemon-add" "$H" && grep -q "audit \"daemon-remove" "$H"'
# post_create est du shell ARBITRAIRE : il doit rester hors du helper privilégié. Le seul
# endroit où le mot a le droit d'apparaître, c'est le commentaire qui dit qu'il n'est pas exécuté.
chk "post_create n apparaît QUE dans un commentaire" \
    '[ "$(grep -c "post_create" "$H")" = "$(grep -c "^#.*post_create" "$H")" ]'

[ "$fails" -eq 0 ] && echo "OK — garde-fous daemon-* (RM2693)" || { echo "ÉCHEC : $fails"; exit 1; }
