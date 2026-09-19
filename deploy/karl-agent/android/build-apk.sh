#!/usr/bin/env bash
# Build de l'APK release signé de l'app « karl » (RM2331) et publication sur le
# karl-agent : https://<serveur>/app/karl-cockpit.apk (route publique, sideload).
#
#   deploy/karl-agent/android/build-apk.sh            # build + publication
#   deploy/karl-agent/android/build-apk.sh --no-publish
#
# Clé de signature : ~/.config/karl-android/{release.jks,signing.properties},
# HORS du repo, créée au premier build (mot de passe aléatoire jamais affiché ni
# passé en argument). À ARCHIVER dans Vaultwarden : sans elle, une mise à jour de
# l'app exige de la désinstaller (Android refuse une signature différente).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
export ANDROID_HOME="${ANDROID_HOME:-/opt/android-sdk}"
SIGN_DIR="${KARL_SIGN_DIR:-$HOME/.config/karl-android}"
PROPS="$SIGN_DIR/signing.properties"
JKS="$SIGN_DIR/release.jks"
PUBLISH=1
[[ "${1:-}" == "--no-publish" ]] && PUBLISH=0

[[ -d "$ANDROID_HOME/platforms" ]] || { echo "✗ SDK Android absent ($ANDROID_HOME)" >&2; exit 1; }

if [[ ! -f "$PROPS" ]]; then
    [[ -e "$JKS" ]] && { echo "✗ $JKS existe sans $PROPS : restaurer les deux depuis Vaultwarden" >&2; exit 1; }
    umask 077
    mkdir -p "$SIGN_DIR"
    pwfile="$(mktemp "$SIGN_DIR/.pw.XXXXXX")"
    trap 'rm -f "$pwfile"' EXIT
    openssl rand -base64 33 | tr -d '\n' >"$pwfile"
    keytool -genkeypair -keystore "$JKS" -storetype PKCS12 -alias karl \
        -keyalg RSA -keysize 4096 -validity 10000 \
        -dname "CN=karl cockpit, O=iProspective, C=FR" \
        -storepass:file "$pwfile" >/dev/null
    { echo "storeFile=$JKS"; echo "storePassword=$(cat "$pwfile")";
      echo "keyAlias=karl"; echo "keyPassword=$(cat "$pwfile")"; } >"$PROPS"
    chmod 600 "$PROPS" "$JKS"
    echo "✓ clé de signature créée : $JKS (+ $PROPS) — À ARCHIVER dans Vaultwarden"
fi

cd "$HERE"
./gradlew --no-daemon -q -Pkarl.signing="$PROPS" assembleRelease
APK="$HERE/app/build/outputs/apk/release/app-release.apk"
[[ -f "$APK" ]] || { echo "✗ APK release absent (signature non configurée ?)" >&2; exit 1; }
BT="$(ls -d "$ANDROID_HOME"/build-tools/* | sort -V | tail -1)"
"$BT/apksigner" verify "$APK"
CERT="$("$BT/apksigner" verify --print-certs "$APK" | sed -n 's/.*certificate SHA-256 digest: //p' | head -1)"
VERSION="$(sed -n 's/.*versionName = "\(.*\)"/\1/p' app/build.gradle.kts)"
echo "✓ APK $VERSION signé : $APK ($(( $(stat -c %s "$APK") / 1024 )) Kio) — certificat SHA-256 $CERT"

if (( PUBLISH )); then
    # l'état du karl-agent EN SERVICE (celui de .mmi-pm-core), pas celui d'un env de dev
    CORE="${PM_CORE_DIR:-/zfs/workspaces/ai/project-management}"
    STATE="$(cd "$CORE" && python3 -c 'import sys; sys.path.insert(0, "scripts"); import pm_stores; print(pm_stores.state_dir())')"
    install -D -m 644 "$APK" "$STATE/app/karl-cockpit.apk"
    echo "✓ publié : $STATE/app/karl-cockpit.apk → <serveur>/app/karl-cockpit.apk"
fi
