#!/usr/bin/env bash
#
# Author:
# 	Keith Gorlen gorlen@comcast.net
#
# Replaces the most recent version of the Duplicacy CLI in the Duplicacy 
# Web UI bin directory with a link to duplicacy-wrapper.py after saving 
# the CLI in DuplicacyLog/bin. 
#
# Links /usr/bin/duplicacy to the CLI saved in DuplicacyLog/bin.
#
# Monitors the Duplicacy Web UI bin directory for changes, keeping the 
# most recent CLI version linked to duplicacy-wrapper.py. 
#
# Removes links to duplicacy-wrapper.py and restores the CLI on exit.
#
CONF=/etc/config/qpkg.conf
QPKG_NAME="DuplicacyLog"
QPKG_ROOT=`/sbin/getcfg $QPKG_NAME Install_Path -f ${CONF}`

set -x
set -e
mkdir -p "$QPKG_ROOT/bin"

WRAP_CLI="$QPKG_ROOT/duplicacy-wrapper.py"
WEBUI_ROOT=`/sbin/getcfg Duplicacy Install_Path -f ${CONF}`
WEBUI_BIN="$WEBUI_ROOT/.duplicacy-web/bin"

# log_alert <message> <severity>
#
# Log <message> to QNAP Notification Center with specified <severity>,
# 0 = Information, 1 = Warning, 2 = Error.
#
# NOTE:
#
# The QNAP log_tool --user, --app_name, and --category options stopped
# setting the respective fields in the System Event Log after firmware
# version 4.4.3.1439(20200925).  Also, the --category option fails with
# an "unrecognized option" error, though the -G alias does not.
#
function log_alert {
	log_tool --append "$1" --type $2 --user $USER --app_name DuplicacyLog -G "App Status Change" || true
}

# newest <directory>
#
# Find newest CLI version in <directory>
#	Assumes duplicacy CLI name format is duplicacy_linux_<arch>_i.j.k,
#	e.g. duplicacy_linux_x64_2.7.2
#
function newest {
	if [ ! -d "$1" ]; then
		echo ""
	else
		version=`ls -1 "$1"/duplicacy_linux_*_* | sed -e 's/.*_//' | sort -r -g -t '.' -k 1,1 -k 2,2 -k 3,3 | head -n 1`
		path=`ls "$1"/duplicacy_linux_*_$version`
		echo `basename ${path:-""}`
	fi
}

# Remove all links to wrapper
#
function unwrap {
	if [ -d "$WEBUI_BIN" ]; then	
		shopt -s nullglob
		for f in "$WEBUI_BIN"/duplicacy_linux_*_*; do
			if [ -h $f -a "`readlink -n "$f"`" == "$WRAP_CLI" ]; then
				rm "$f"
				mv "$QPKG_ROOT/bin/"`basename $f` "$WEBUI_BIN"
				log_alert "[DuplicacyLog] $f unlinked from wrapper script" 0
			fi
		done
	fi

	rm -f "$QPKG_ROOT/bin/"duplicacy_linux_*_*
}

# Cleanup on exit
#
sighandler() {
	trap - EXIT
	unwrap

	rm -f /usr/bin/duplicacy
	CLI="$(newest "$WEBUI_BIN")"
	if [ -x "$WEBUI_BIN/$CLI" ]; then
		ln -s "$WEBUI_BIN/$CLI" /usr/bin/duplicacy
		log_alert "[DuplicacyLog] /usr/bin/duplicacy linked to $WEBUI_BIN/$CLI" 0
	else
		log_alert "[DuplicacyLog] duplicacy CLI missing or not executable" 1
	fi

	exit 0
}

trap sighandler EXIT

while [ -d "$WEBUI_BIN" ]; do
	CLI="$(newest "$WEBUI_BIN")"
	if [ ! -h "$WEBUI_BIN/$CLI" -o "`readlink -n "$WEBUI_BIN/$CLI"`" != "$WRAP_CLI" ]; then
		unwrap

# Move newest version of duplicacy CLI to .../DuplicacyLog/bin/
# Link newest version in .../DuplicacyLog/bin to /usr/bin/duplicacy
# Link duplicacy-wrapper.py to newest version in .../Duplicacy/.duplicacy-web/bin/

		mv "$WEBUI_BIN/$CLI" "$QPKG_ROOT/bin"
		rm -f /usr/bin/duplicacy
		ln -s "$QPKG_ROOT/bin/$CLI" /usr/bin/duplicacy
		ln -s "$WRAP_CLI" "$WEBUI_BIN/$CLI"
		log_alert "[DuplicacyLog] $CLI linked to wrapper; /usr/bin/duplicacy linked to $QPKG_ROOT/bin/$CLI" 0
	fi

	inotifywait -e close_write -e move -e delete -e move_self -e delete_self "$WEBUI_BIN"
done

log_alert "[DuplicacyLog] $WEBUI_BIN does not exist; duplicacyln.sh exiting" 2