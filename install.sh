#!/bin/sh -e
# Registers the native host for your user, writes a default config if you have none, and builds the unsigned xpi.
D=$(cd "$(dirname "$0")" && pwd)
case "$(uname)" in
  Darwin) NMH="$HOME/Library/Application Support/Mozilla/NativeMessagingHosts" ;;
  *)      NMH="$HOME/.mozilla/native-messaging-hosts" ;;
esac
mkdir -p "$NMH"
sed "s|@HOST@|$D/host/wtfisthis-host|" "$D/host/wtfisthis.json" > "$NMH/wtfisthis.json"
chmod +x "$D/host/wtfisthis-host"
CFG="${WTFISTHIS_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/wtfisthis/config.json}"
if [ ! -f "$CFG" ]; then
  mkdir -p "$(dirname "$CFG")"
  sed "s|@TERMINAL@|${TERMINAL:-xterm}|" "$D/config.example.json" > "$CFG"
  echo "wrote default config: $CFG  <- pick your agent preset and terminal there"
fi
rm -f "$D/wtfisthis.xpi"; (cd "$D/ext" && zip -qr "$D/wtfisthis.xpi" . -x '.*')
echo "native host registered: $NMH/wtfisthis.json"
echo "xpi built: $D/wtfisthis.xpi  (unsigned; load ext/manifest.json via about:debugging, or sign it with web-ext)"
