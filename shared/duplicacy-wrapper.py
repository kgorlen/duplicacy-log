#!/usr/bin/env python
'''
Wrapper for duplicacy CLI to log QNAP notifications

Author:

	Keith Gorlen
	gorlen@comcast.net

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

	NOTE: Use of whitespace in the -comment option currently causes an error due to a Web UI bug.

References:
	https://docs.python.org/2/library/subprocess.html

'''
from __future__ import print_function
import os
import os.path
import subprocess
import signal
import sys
import getpass
import socket
import urllib2
import re

# Global constants

CMD = ' '.join(sys.argv[1:])	# Running duplicacy command
USER = getpass.getuser()		# Current user name
KEYWORDS = set(['BACKUP_END', 'BACKUP_STATS',	# Keywords for statistics report
			'SNAPSHOT_COPY', 'SNAPSHOT_NONE', 'SNAPSHOT_CHECK',
			'RESTORE_END', 'RESTORE_STATS'])

# Global variables

at_start = False				# Log INFO message when starting duplicacy
cli = None						# duplicacy subprocess Popen object
healthchecks = None				# Healthchecks.io URL
msg = ''						# Log message
operation = None				# 'backup', 'copy', 'prune', 'check', or 'restore'
stats = ''						# Statistics report
verbose = False					# Log WARN and ERROR messages
errors = 0						# ERROR count
warnings = 0					# WARN count
chunks_removed = 0				# Count of chunks removed by prune
snapshots_removed = 0			# Count of snapshots removed by prune

def signal_handler(signum, frame):
	'''
	Propagate signals to duplicacy subprocess
	
	References:
		https://docs.python.org/2/library/signal.html#module-signal
	'''
	if cli is None:
		sys.exit(1)

	os.kill(cli.pid, signum)

def log_tool(message, severity):
	'''
	Log <message> to QNAP Notification Center with specified <severity>,
	0 = Information, 1 = Warning, 2 = Error.
	
	NOTE:
	
	The QNAP log_tool --category option fails with an "unrecognized option"
	error, though the -G alias does not. 
	
	'''
	args = ['log_tool',
		'--append', message,
		'--type', str(severity),
		'--user', USER,
		'--app_name', 'Duplicacy',
		'-G', 'Job Status']

	if subprocess.call(args):
		assert False, 'log_tool({}) failed'.format(args)

def exec_unwrapped():
	'''
	Execute duplicacy without wrapping/notifications
	'''
	os.execvp('duplicacy', ['duplicacy'] + sys.argv[1:])	# os.execvp() does not return

# Parse duplicacy global options and command:

i = 1
while i < len(sys.argv):
	if sys.argv[i] in ('-profile', '-suppress'):
		i += 2		# skip global option and value
	elif sys.argv[i] == '-comment':
		if 'log_at_start' in sys.argv[i + 1]:
			at_start = True
		if 'log_verbose' in sys.argv[i + 1]:
			verbose = True
		m = re.search(r'\bhealthchecks\s*=\s*(https://.*[0-9a-f]+\b)', sys.argv[i + 1])
		if m:
			healthchecks = m.group(1)
		i += 2		# skip global option and value
	elif sys.argv[i][0] == '-':
		i += 1		# skip global option
	elif sys.argv[i] in ('backup', 'copy', 'prune', 'check', 'restore'):
		operation = sys.argv[i]
		break
	elif sys.argv[i] in ('init', 'list', 'cat', 'diff', 'history', 'password',
						'add', 'set', 'info', 'benchmark', 'help', 'h'):
		exec_unwrapped()	# no notification for other operations
	else:
		log_tool('[duplicacy] Unrecogized command: {}'.format(CMD), 1)
		exec_unwrapped()
else:
	log_tool('[duplicacy] Parse failed: {}'.format(CMD), 1)
	exec_unwrapped()

# Start duplicacy:

if at_start:
	log_tool('[duplicacy starting {}] {}'.format(operation, CMD), 0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
cli = subprocess.Popen(['duplicacy'] + sys.argv[1:], bufsize=1, stdout=subprocess.PIPE)

# Process duplicacy output:

while True:
	line = cli.stdout.readline()
	if line == '' and cli.poll() is not None:
		break

	print(line, end='')		# repeat to Web UI
	sys.stdout.flush()
	
#                        Y Y Y Y- M M- D D    H H: m m: s s . S S S
	if not re.match(r'\d\d\d\d-\d\d-\d\d\s+\d\d:\d\d:\d\d\.\d\d\d\b', line):
		continue			# skip e.g. check -tabular lines

	m = re.search(r'\bSTORAGE_SET\s+.*set to\s+(.*)$', line)
	if m: msg += '; Storage: ' + m.group(1)
		
	m = re.search(r'\bREPOSITORY_SET\s+.*set to\s+(.*)$', line)
	if m: msg += '; Repository: ' + m.group(1)

	if re.search(r'\bWARN\b', line):
		warnings += 1
		if verbose:
			log_tool('[duplicacy {}] {}; {}'.format(operation, CMD, line), 1)
		
	if re.search(r'\b(ERROR|FATAL|ASSERT)\b', line):
		errors += 1
		if verbose:
			log_tool('[duplicacy {}] {}; {}'.format(operation, CMD, line), 2)
			
	if operation == 'prune':
		if re.search(r'\bINFO\s+CHUNK_DELETE\b', line):
			chunks_removed += 1
		elif re.search(r'\bINFO\s+SNAPSHOT_DELETE\b.*\bremoved\b', line):
			snapshots_removed += 1

	m = re.search(r'\bINFO\s+(\w+)\s+(\w.+\w)$', line)
	if m and m.group(1) in KEYWORDS:
		if m.group(1) == 'SNAPSHOT_CHECK' and re.search(r'All chunks referenced by snapshot', m.group(2)):
			pass
		elif m.group(1) == 'SNAPSHOT_COPY' and not re.search(r'Chunks to copy:|Copied \d+ new chunks', m.group(2)):
			pass
		else:
			stats += '; ' + m.group(2)

# Format and log message:

# References:
#	https://github.com/gilbertchen/duplicacy/wiki/Exit-Codes

if errors > 0:
	severity = 2
	msg += '; {} errors(s)'.format(errors)
elif cli.poll() == 0:
	severity = 0			# Information: backup was successful
elif cli.poll() == 1:
	severity = 1			# Warning: command was interrupted
elif cli.poll() == 2:
	severity = 2			# Error: command arguments are malformed
elif cli.poll() == 3:
	severity = 2			# Error: invalid value for a command argument
elif cli.poll() == 100:
	severity = 2			# Error: most run-time errors, including those from failed connections
elif cli.poll() == 101:
	severity = 2			# Error: command encountered an error in a dependency library used by Duplicacy
else:
	severity = 2			# Error: other errors

if warnings > 0:
	msg += '; {} warning(s)'.format(warnings)
	if severity == 0:
		severity = 1

if chunks_removed > 0:
	stats += '; {} chunk(s) removed'.format(chunks_removed)
	
if snapshots_removed > 0:
	stats += '; {} snapshot(s) removed'.format(snapshots_removed)

msg += stats

if cli.poll() > 0:
	msg += '; Exit status: {}'.format(cli.poll())

log_tool('[duplicacy {}] {}{}'.format(operation, CMD, msg), severity)

if healthchecks:	# https://healthchecks.io/docs/
	try:
		urllib2.urlopen('{}/{}'.format(healthchecks, severity),
			data='[duplicacy {}] {}{}'.format(operation, CMD, msg),
			timeout=10)
	except (urllib2.URLError, socket.error) as e:
		log_tool('[duplicacy {}] {} ping failed: {}'.format(operation, healthchecks, e), 1)

sys.exit(cli.poll())
