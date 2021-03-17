#!/bin/sh
CONF=/etc/config/qpkg.conf
QPKG_NAME="DuplicacyLog"
QPKG_ROOT=`/sbin/getcfg $QPKG_NAME Install_Path -f ${CONF}`
APACHE_ROOT=`/sbin/getcfg SHARE_DEF defWeb -d Qweb -f /etc/config/def_share.info`
export QNAP_QPKG=$QPKG_NAME

# Get PID of duplicacyln.sh process:
PID="`ps -ef | grep duplicacyln.sh | grep -v grep | awk '{print $1}'`"

case "$1" in
  start)
    ENABLED=$(/sbin/getcfg $QPKG_NAME Enable -u -d FALSE -f $CONF)
    if [ "$ENABLED" != "TRUE" ]; then
        echo "$QPKG_NAME is disabled."
        exit 1
    fi
    : ADD START ACTIONS HERE
	if [ -z $PID ]; then
		$QPKG_ROOT/duplicacyln.sh 1>"$QPKG_ROOT/duplicacyln.log" 2>&1 &
	fi
    ;;

  stop)
    : ADD STOP ACTIONS HERE
	if [ -n $PID ]; then
		kill $PID
		wait $PID
	fi
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
