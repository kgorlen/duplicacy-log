#!/usr/bin/env python
# pylint: disable=consider-using-f-string,pointless-string-statement,invalid-name
"""
Wrapper for duplicacy CLI to log QNAP notifications

Author:
        Keith Gorlen
        kgorlen@gmail.com

Captures the output and exit status of duplicacy backup, copy, prune,
check, and restore commands, logs a summary message to the QNAP
Notification Center, and optionally posts to healthchecks.io.

Installation:

        1. Move latest version of duplicacy CLI from .duplicacy-web/bin to another directory.

        2. Link /usr/bin/duplicacy to saved CLI.

        3. Move or link duplicacy-wrapper.py to .duplicacy-web/bin.

        See DuplicacyLog.sh for an example.

Use:

        Same as duplicacy CLI, plus the following may be set in the -comment global option:

        log_at_start		Log an Information message when starting duplicacy
        log_verbose			Log individual WARN and ERROR messages
        healthchecks=<url>	Send pings to healthchecks.io

        NOTE: Use of whitespace in the -comment option currently causes an error
        due to a Web UI bug.

References:
        https://forum.duplicacy.com/
        https://docs.python.org/2/library/subprocess.html
        https://healthchecks.io/docs/

"""
from __future__ import print_function
import os
import os.path
import subprocess
import signal
import sys
import getpass
import re

__author__ = "Keith Gorlen"

# Global constants

CMD = " ".join(sys.argv[1:])  # Running duplicacy command
USER = getpass.getuser()  # Current user name
KEYWORDS = set(
    [
        "BACKUP_END",
        "BACKUP_STATS",  # Keywords for statistics report
        "SNAPSHOT_COPY",
        "SNAPSHOT_NONE",
        "SNAPSHOT_CHECK",
        "RESTORE_END",
        "RESTORE_STATS",
    ]
)

# Global variables

CLI = None
"""duplicacy subprocess Popen object."""
OPERATION = "?"
""" 'backup', 'copy', 'prune', 'check', or 'restore'."""


def signal_handler(signum, frame):  # pylint: disable=unused-argument
    """
    Propagate signals to duplicacy subprocess.

    Arguments:
                signum -- signal number
        frame -- current stack frame (unused)

    Note:
            https://docs.python.org/2/library/signal.html#module-signal
    """

    if CLI is None:
        sys.exit(1)

    os.kill(CLI.pid, signum)


def log_tool(message, severity):
    """Log message to QNAP Notification Center.

    Arguments:
        message -- message string
        severity -- severity level: 0 = Information, 1 = Warning, 2 = Error.

    Raises:
        RuntimeError: If log_tool command fails.

    Notes:
        The QNAP log_tool --category option fails with an "unrecognized option"
        error, though the -G alias does not.

        Modify this function if your system does not support log_tool.

    """
    args = [
        "log_tool",
        "--append", message,
        "--type", str(severity),
        "--user", USER,
        "--app_name", "Duplicacy",
        "-G", "Job Status",
    ]

    if subprocess.call(args):
        raise RuntimeError("log_tool({}) failed".format(args))


def exec_unwrapped():
    """Execute duplicacy without wrapping/notifications."""

    os.execvp("duplicacy", ["duplicacy"] + sys.argv[1:])  # os.execvp() does not return


def ping_healthchecks(url, data="", timeout=10):
    """Send ping to healthchecks.io: https://healthchecks.io/docs/.

    Arguments:
                url -- healthchecks.io URL with unique ping code
                data -- optional data to include in the ping
                timeout -- timeout for the ping request (default: 10 seconds)
    """

    # Ensure data is bytes on py3 urlopen
    if data and not isinstance(data, bytes):
        data = data.encode("utf-8")

    cmd = ["curl", "-fsS", "--max-time", str(timeout), "--retry", "5", "-o", "/dev/null"]
    if data:
        cmd += ["--data-raw", data]
    cmd.append(url)

    try:
        result = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE
        )
        err = result.communicate()[1]

        if result.returncode != 0:
            log_tool(
                "[duplicacy {}] {} ping failed, {}".format(
                    OPERATION, url, err.decode("utf-8", errors="ignore")
                ),
                1,
            )

    except OSError as e:
        raise OSError("curl not found or error: %s" % str(e))  # pylint: disable=raise-missing-from


def main():
    """Parse duplicacy global options and command, start duplicacy,
    process output, and log summary message to QNAP Notification Center.

    Raises:
        RuntimeError: If duplicacy subprocess is not initialized
        RuntimeError: If duplicacy subprocess has no stdout (use stdout=PIPE)
        RuntimeError: If stdout line is not str or bytes
    """

    global CLI, OPERATION  # pylint: disable=global-statement

    at_start = False
    """Log INFO message when starting duplicacy"""
    healthchecks = None
    """Healthchecks.io URL"""
    msg = ""
    """Log message"""
    repository = None
    """Repository name"""
    storage = None
    """Storage name"""
    stats = ""
    """Statistics report"""
    verbose = False
    """Log WARN and ERROR messages"""
    errors = 0
    """ERROR count"""
    warnings = 0
    """WARN count"""
    chunks_removed = 0
    """Count of chunks removed by prune"""
    snapshots_removed = 0
    """Count of snapshots removed by prune"""

    # Parse duplicacy global options and command

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] in ("-profile", "-suppress"):
            i += 2  # skip global option and value
        elif sys.argv[i] == "-comment":
            if "log_at_start" in sys.argv[i + 1]:
                at_start = True
            if "log_verbose" in sys.argv[i + 1]:
                verbose = True
            m = re.search(
                r"\bhealthchecks\s*=\s*([^,'\"\s]+)", sys.argv[i + 1]
            )
            if m:
                healthchecks = m.group(1)
            i += 2  # skip global option and value
        elif sys.argv[i][0] == "-":
            i += 1  # skip global option
        elif sys.argv[i] in ("backup", "copy", "prune", "check", "restore"):
            OPERATION = sys.argv[i]
            break
        elif sys.argv[i] in (
            "init",
            "list",
            "cat",
            "diff",
            "history",
            "password",
            "add",
            "set",
            "info",
            "benchmark",
            "help",
            "h",
        ):
            exec_unwrapped()  # no notification for other operations
        else:
            log_tool("[duplicacy] Unrecogized command: {}".format(CMD), 1)
            exec_unwrapped()
    else:
        log_tool("[duplicacy] Parse failed: {}".format(CMD), 1)
        exec_unwrapped()

    # Start duplicacy:

    if at_start:
        log_tool("[duplicacy starting {}] {}".format(OPERATION, CMD), 0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    CLI = subprocess.Popen(
        ["duplicacy"] + sys.argv[1:], bufsize=1, stdout=subprocess.PIPE
    )

    if CLI is None:
        raise RuntimeError("duplicacy subprocess is not initialized")

    if CLI.stdout is None:
        raise RuntimeError("duplicacy subprocess has no stdout (use stdout=PIPE)")

    # Process duplicacy output:

    while True:
        raw = CLI.stdout.readline()

        if not raw and CLI.poll() is not None:
            break  # None/empty read and process has terminated

        if isinstance(raw, str):
            line = raw
        elif isinstance(raw, (bytes, bytearray)):  # Decode bytes/bytearray on Python 3/2
            line = raw.decode("utf-8", "replace")
        else:
            raise RuntimeError("stdout line is not str or bytes: {}".format(type(raw)))

        print(line, end="")  # repeat to Web UI
        sys.stdout.flush()

        #                        Y Y Y Y- M M- D D    H H: m m: s s . S S S
        if not re.match(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\b", line):
            continue  # skip e.g. check -tabular lines

        m = re.search(r"\bSTORAGE_SET\s+.*set to\s+(.*)$", line)
        if m:
            storage = m.group(1)
            msg += "; Storage: " + storage

        m = re.search(r"\bREPOSITORY_SET\s+.*set to\s+(.*)$", line)
        if m:
            repository = m.group(1)
            msg += "; Repository: " + repository

        if re.search(r"\bWARN\b", line):
            warnings += 1
            if verbose:
                log_tool("[duplicacy {}] {}; {}".format(OPERATION, CMD, line), 1)

        if re.search(r"\b(ERROR|FATAL|ASSERT)\b", line):
            errors += 1
            if verbose:
                log_tool("[duplicacy {}] {}; {}".format(OPERATION, CMD, line), 2)

        if OPERATION == "prune":
            if re.search(r"\bINFO\s+CHUNK_DELETE\b", line):
                chunks_removed += 1
            elif re.search(r"\bINFO\s+SNAPSHOT_DELETE\b.*\bremoved\b", line):
                snapshots_removed += 1

        m = re.search(r"\bINFO\s+(\w+)\s+(\w.+\w)$", line)
        if m and m.group(1) in KEYWORDS:
            if m.group(1) == "SNAPSHOT_CHECK" and re.search(
                r"All chunks referenced by snapshot", m.group(2)
            ):
                pass
            elif m.group(1) == "SNAPSHOT_COPY" and not re.search(
                r"Chunks to copy:|Copied \d+ new chunks", m.group(2)
            ):
                pass
            else:
                stats += "; " + m.group(2)

    # Format and log message:

    # References:
    # 	https://github.com/gilbertchen/duplicacy/wiki/Exit-Codes

    exit_code = CLI.poll() if CLI is not None else 1

    if errors > 0:
        severity = 2
        msg += "; {} errors(s)".format(errors)
    elif exit_code == 0:
        severity = 0  # Information: backup was successful
    elif exit_code == 1:
        severity = 1  # Warning: command was interrupted
    elif exit_code == 2:
        severity = 2  # Error: command arguments are malformed
    elif exit_code == 3:
        severity = 2  # Error: invalid value for a command argument
    elif exit_code == 100:
        severity = (
            2  # Error: most run-time errors, including those from failed connections
        )
    elif exit_code == 101:  # Error: command encountered an error
        severity = 2  # in a dependency library used by Duplicacy
    else:
        severity = 2  # Error: other errors

    if warnings > 0:
        msg += "; {} warning(s)".format(warnings)
        if severity == 0:
            severity = 1

    if chunks_removed > 0:
        stats += "; {} chunk(s) removed".format(chunks_removed)

    if snapshots_removed > 0:
        stats += "; {} snapshot(s) removed".format(snapshots_removed)

    msg += stats

    if exit_code is not None and exit_code > 0:
        msg += "; Exit status: {}".format(exit_code)

    log_tool("[duplicacy {}] {}{}".format(OPERATION, CMD, msg), severity)

    if healthchecks:
        ping_healthchecks(
            "{}/{}".format(healthchecks, severity),
            data="[duplicacy {}] {}{}".format(OPERATION, CMD, msg),
            timeout=10,
        )

    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # pylint: disable=broad-exception-caught
        log_tool("[duplicacy {}] {}: {}".format(OPERATION, CMD, e), 2)
        sys.exit(1)
