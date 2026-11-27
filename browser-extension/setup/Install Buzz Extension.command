#!/bin/zsh
# Standalone macOS setup: only built-in system tools, no Python or source checkout.
set -euo pipefail
umask 077

fail() { print -u2 -- "Buzz setup: $1"; exit 1; }
[[ "$(/usr/bin/uname -s)" == Darwin ]] || fail "This installer requires macOS."

package_dir="${0:A:h}"
app_path="${BUZZ_SETUP_APP_PATH:-/Applications/Buzz.app}"
install_home="${BUZZ_SETUP_HOME:-$HOME}"
host_name="com.mahmoudbasuony.buzz"
extension_id="mlaagfgpblngahdpkgkeocdfbndnodgb"
origin="chrome-extension://${extension_id}/"
payload="${package_dir}/extension"
executable="${app_path}/Contents/MacOS/Buzz"
info="${app_path}/Contents/Info.plist"

[[ -x "$executable" && -f "$info" ]] || fail "Install Buzz.app in Applications first. / ثبّت Buzz في Applications أولًا."
[[ "$(/usr/bin/plutil -extract MBBrowserBridgeProtocol raw -o - "$info" 2>/dev/null)" == 1 ]] || fail "Update Buzz using the matching release first. / حدّث Buzz من صفحة الإصدارات أولًا."
[[ "$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$info" 2>/dev/null)" == com.chidiwilliams.buzz ]] || fail "This application is not Buzz."
for file in manifest.json popup.html popup.js popup.css icon.png; do
  [[ -f "${payload}/${file}" && ! -L "${payload}/${file}" ]] || fail "Incomplete setup package: ${file}. Extract the ZIP first."
done
public_key="$(/usr/bin/plutil -extract key raw -o - "${payload}/manifest.json")"
actual_id="$(print -rn -- "$public_key" | /usr/bin/base64 -D | /usr/bin/shasum -a 256 | /usr/bin/cut -c 1-32 | /usr/bin/tr '0123456789abcdef' 'abcdefghijklmnop')"
[[ "$actual_id" == "$extension_id" ]] || fail "The extension identity does not match Buzz."

support="${install_home}/Library/Application Support/Buzz"
destination="${support}/Chrome"
bridge="${support}/browser-bridge"
hosts="${install_home}/Library/Application Support/Google/Chrome/NativeMessagingHosts"
host_file="${hosts}/${host_name}.json"
enabled_file="${bridge}/enabled.json"
for candidate in "$support" "$destination" "$bridge" "$hosts" "$host_file" "$enabled_file"; do
  [[ ! -L "$candidate" ]] || fail "Refusing a symbolic link at ${candidate}."
done
[[ ! -e "$destination" || -f "${destination}/.buzz-managed" ]] || fail "The Chrome setup folder already contains other files: ${destination}"

/bin/mkdir -p "$support" "$bridge" "$hosts"
/bin/chmod 700 "$bridge"
stage="$(/usr/bin/mktemp -d "${support}/.chrome-setup.XXXXXX")"
swapped=0
committed=0
cleanup() {
  local exit_code=$?
  if (( ! committed && swapped )); then
    /bin/rm -rf "$destination"
    [[ ! -d "${stage}/previous" ]] || /bin/mv "${stage}/previous" "$destination"
  fi
  /bin/rm -rf "$stage"
  return "$exit_code"
}
trap cleanup EXIT

/bin/mkdir "${stage}/new"
/usr/bin/ditto "$payload" "${stage}/new/extension"
/usr/bin/ditto "${package_dir}/Quick Start.html" "${stage}/new/Quick Start.html"
print -r -- "$host_name" > "${stage}/new/.buzz-managed"

/usr/bin/plutil -create xml1 "${stage}/host.json"
/usr/bin/plutil -insert name -string "$host_name" "${stage}/host.json"
/usr/bin/plutil -insert description -string 'Send a YouTube video to Buzz' "${stage}/host.json"
/usr/bin/plutil -insert path -string "$executable" "${stage}/host.json"
/usr/bin/plutil -insert type -string stdio "${stage}/host.json"
/usr/bin/plutil -insert allowed_origins -json "[\"${origin}\"]" "${stage}/host.json"
/usr/bin/plutil -convert json "${stage}/host.json"
print -r -- "{\"enabled\":true,\"origin\":\"${origin}\"}" > "${stage}/enabled.json"
/bin/chmod 600 "${stage}/host.json" "${stage}/enabled.json"

[[ ! -d "$destination" ]] || /bin/mv "$destination" "${stage}/previous"
swapped=1
/bin/mv "${stage}/new" "$destination"
# Native messaging reads this path; no API credential or transcript is accessed.
/bin/mv "${stage}/host.json" "$host_file"
/bin/mv "${stage}/enabled.json" "$enabled_file"
committed=1

print -- '\n✓ Setup completed. / اكتمل إعداد الربط.'
print -- 'Quit and reopen Buzz once after setup. / اقفل Buzz وافتحه تاني مرة واحدة بعد التثبيت.'
print -- 'In Chrome, open chrome://extensions and enable Developer mode.'
print -- 'Choose Load unpacked, press Command+Shift+G, then paste this folder:'
print -r -- "${destination}/extension"
print -- '\nحمّل الإضافة من المجلد أعلاه مرة واحدة، ثم ثبّت أيقونتها بجوار شريط العنوان.'
print -- 'If Buzz is already loaded from another folder, remove that extension first.'
print -- 'You can delete the downloaded setup folder after installation.'
if [[ "${BUZZ_SETUP_NO_OPEN:-0}" != 1 ]]; then
  /usr/bin/open "${destination}/extension"
fi
