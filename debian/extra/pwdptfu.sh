#!/bin/bash
export TEXTDOMAIN=pt-firmware-updater

# shellcheck disable=SC1091
. gettext.sh

zenity --password --title "$(gettext "Password Required")"
