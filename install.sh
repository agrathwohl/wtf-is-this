#!/bin/sh -e
# Registers the native host with Firefox and every Chromium-family browser you have a profile for,
# writes a default config if you have none, and builds the extension zips.
D=$(cd "$(dirname "$0")" && pwd)
chmod +x "$D/host/wtfisthis-host"
# Chrome derives the extension id from the "key" in chrome/manifest.json: sha256 of the DER public key, first 32 hex digits spelled a-p.
# Installed from the Web Store under a different id? Run: WTFISTHIS_CHROME_ID=<that id> ./install.sh
CHROME_ID=$WTFISTHIS_CHROME_ID
case "$(uname)" in
  Darwin) FF="$HOME/Library/Application Support/Mozilla/NativeMessagingHosts"; CR="$HOME/Library/Application Support"; CHROMIUMS="Google/Chrome:Chromium:BraveSoftware/Brave-Browser:Microsoft Edge" ;;
  *)      FF="$HOME/.mozilla/native-messaging-hosts"; CR="${XDG_CONFIG_HOME:-$HOME/.config}"; CHROMIUMS="google-chrome:chromium:BraveSoftware/Brave-Browser:microsoft-edge" ;;
esac
mkdir -p "$FF"
sed "s|@HOST@|$D/host/wtfisthis-host|" "$D/host/wtfisthis.json" > "$FF/wtfisthis.json"
echo "firefox: host registered at $FF/wtfisthis.json"
IFS=:
for B in $CHROMIUMS; do
  [ -d "$CR/$B" ] || continue
  [ -n "$CHROME_ID" ] || CHROME_ID=$(uv run --no-project python -c 'import base64,hashlib,json,sys;print(hashlib.sha256(base64.b64decode(json.load(open(sys.argv[1]))["key"])).hexdigest()[:32].translate(str.maketrans("0123456789abcdef","abcdefghijklmnop")))' "$D/chrome/manifest.json")
  mkdir -p "$CR/$B/NativeMessagingHosts"
  sed -e "s|@HOST@|$D/host/wtfisthis-host|" -e "s|@ID@|$CHROME_ID|" "$D/host/wtfisthis-chrome.json" > "$CR/$B/NativeMessagingHosts/wtfisthis.json"
  echo "$B: host registered at $CR/$B/NativeMessagingHosts/wtfisthis.json (extension id $CHROME_ID)"
done
unset IFS
CFG="${WTFISTHIS_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/wtfisthis/config.json}"
if [ ! -f "$CFG" ]; then
  mkdir -p "$(dirname "$CFG")"
  sed "s|@TERMINAL@|${TERMINAL:-xterm}|" "$D/config.example.json" > "$CFG"
  echo "wrote default config: $CFG  <- pick your agent preset and terminal there"
fi
rm -f "$D/wtfisthis.xpi" "$D/wtfisthis-chrome.zip"
(cd "$D/ext" && zip -qr "$D/wtfisthis.xpi" . -x '.*')
T=$(mktemp -d); cp -RL "$D/chrome/." "$T"; sed '/"key":/d' "$D/chrome/manifest.json" > "$T/manifest.json"
(cd "$T" && zip -qr "$D/wtfisthis-chrome.zip" . -x '.*'); rm -rf "$T"
echo "firefox: $D/wtfisthis.xpi built (unsigned; load ext/manifest.json via about:debugging, or sign it with web-ext)"
echo "chrome:  chrome://extensions -> Developer mode -> Load unpacked -> $D/chrome   ($D/wtfisthis-chrome.zip is the Web Store upload, manifest without the key)"
