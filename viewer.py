# This program takes a tree/list command as an input and updates itself every
# 30 minutes, or whenever the database changed.

import sqlite3
import argparse
import commands
import time
import pyinotify


con = sqlite3.connect("file:tasks.db?mode=ro", uri=True)
con.row_factory = sqlite3.Row
cur = con.cursor()

parser = argparse.ArgumentParser(prog='scryviewer')
parser.add_argument('command', type=str)
args = parser.parse_args()

words = args.command.split(' ')
command = words[0]
tail = [] if len(words) == 0 else words[1:]

wm = pyinotify.WatchManager()
wm.add_watch('tasks.db', pyinotify.IN_MODIFY)
notifier = pyinotify.Notifier(wm, timeout=60*1000)

commands.load_commands(cur)
notifier.loop(callback=lambda n: commands.call_cmd(cur, command, tail))
