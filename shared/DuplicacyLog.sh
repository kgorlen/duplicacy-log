#!/bin/sh
CONF=/etc/config/qpkg.conf
QPKG_NAME="DuplicacyLog"
QPKG_ROOT=`/sbin/getcfg $QPKG_NAME Install_Path -f ${CONF}`
APACHE_ROOT=`/sbin/getcfg SHARE_DEF defWeb -d Qweb -f /etc/config/def_share.info`
export QNAP_QPKG=$QPKG_NAME

set -e
WRAP_CLI="$QPKG_ROOT/duplicacy-wrapper.py"
WEBUI_ROOT=`/sbin/getcfg Duplicacy Install_Path -f ${CONF}`
WEBUI_BIN="$WEBUI_ROOT/.duplicacy-web/bin"

# Find newest CLI version
#	Assumes duplicacy CLI name format is duplicacy_linux_<arch>_i.j.k,
#	e.g. duplicacy_linux_x64_2.7.2

function newest {
	version=`ls -1 "$1"/duplicacy_linux_* | sed -e 's/.*_//' | sort -r -g -t '.' -k 1,1 -k 2,2 -k 3,3 | head -n 1`
	path=`ls "$1"/duplicacy_linux_*_$version`
	CLI=`basename $path`
}

case "$1" in
  start)
    ENABLED=$(/sbin/getcfg $QPKG_NAME Enable -u -d FALSE -f $CONF)
    if [ "$ENABLED" != "TRUE" ]; then
        echo "$QPKG_NAME is disabled."
        exit 1
    fi

# Move newest version of duplicacy CLI to .../DuplicacyLog/bin/
# Link newest version in .../DuplicacyLog/bin to /usr/bin/duplicacy
# Link duplicacy-wrapper.py to newest version in .../Duplicacy/.duplicacy-web/bin/

	newest "$WEBUI_BIN"

	if [ -h "$WEBUI_BIN/$CLI" ]
	then
		echo "$WEBUI_BIN/$CLI already wrapped"
		exit 1
	fi

	if [ ! -e "$WEBUI_BIN/$CLI" ]
	then
		echo "Duplicacy executable $QPKG_ROOT/bin/$CLI missing"
		exit 1
	fi

	mkdir -p "$QPKG_ROOT/bin"
	mv "$WEBUI_BIN/$CLI" "$QPKG_ROOT/bin"
	rm -f /usr/bin/duplicacy
	ln -s "$QPKG_ROOT/bin/$CLI" /usr/bin/duplicacy
	ln -s "$WRAP_CLI" "$WEBUI_BIN/$CLI"
    ;;

  stop)	# Reverse changes made by start

	newest "$QPKG_ROOT/bin"

	if [ ! -h "$WEBUI_BIN/$CLI" ]
	then
		echo "$WEBUI_BIN/$CLI already unwrapped"
		exit 1
	fi

	if [ ! -e "$QPKG_ROOT/bin/$CLI" ]
	then
		echo "Real duplicacy executable $QPKG_ROOT/bin/$CLI missing"
		exit 1
	fi

	rm "$WEBUI_BIN/$CLI"
	mv "$QPKG_ROOT/bin/$CLI" "$WEBUI_BIN"
	rm -f /usr/bin/duplicacy
	ln -s "$WEBUI_BIN/$CLI" /usr/bin/duplicacy
    ;;

  restart)
    $0 stop
    $0 start
    ;;

  *)
    echo "Usage: $0 {start|stop|restart}"
    exit 1
esac

exit 0
