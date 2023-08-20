from prompt_toolkit import print_formatted_text as print
from prompt_toolkit import prompt, PromptSession
import sqlite3
import argparse
import shutil
import pyinotify
import platformdirs

from commands import *
import context


def prompt_input(session, ctx):
    commands.reload_autocomplete()
    working_desc = '/' if ctx.working_task is None else ctx.working_task.desc
    if len(working_desc) > 20:
        working_desc = working_desc[:18]+'...'

    term_size = shutil.get_terminal_size((80, 20))
    if term_size[1] > 8:
        return session.prompt("["+working_desc+"] > ", completer=commands.completer).strip()
    else:
        return session.prompt("["+working_desc+"] > ").strip()



def_location = platformdirs.user_data_dir('scrytask', ensure_exists=True)+'/tasks.db'

parser = argparse.ArgumentParser(prog='scrytask', description='A minimal terminal-based task manager')
parser.add_argument('-i', '--interactive', action='store_true', help="Runs a interactive shell")
parser.add_argument('-v', '--view', type=str, nargs='?', default='', help="Runs a command whenever the database updates")
parser.add_argument('-c', '--command', type=str, nargs='+', default=[], help="Run the commands specified after")
parser.add_argument('-w', '--whitelist', type=str, default=None, help="Limit commands allowed to be used")
parser.add_argument('--database', type=str, default=def_location, help="Path to the database")
parser.add_argument('--no-wrap', action='store_true', default=False, help="Do not wrap text")
args = parser.parse_args()
print("Using database at:", args.database)
con = sqlite3.connect(args.database)
con.row_factory = sqlite3.Row
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS tasks\
             (uuid INTEGER PRIMARY KEY,\
              parent INTEGER,\
              desc TEXT,\
              tags TEXT,\
              status TEXT,\
              start TEXT,\
              due TEXT,\
              repeat TEXT,\
              gauge REAL,\
              created TEXT,\
              depends TEXT)")



ctx = context.Context(cur)


whitelist = None if args.whitelist is None else args.whitelist.split(',')
commands = CommandManager(ctx, whitelist, args.no_wrap)

for i in args.command:
    try:
        commands.call_cmd(i)
        con.commit()
    except AssertionError:
        print("Assertion not satisfied, cancelling command.")

session = PromptSession()

if args.view != '':
    if args.view is None:
        args.view = 'list'

    if not args.interactive:
        wm = pyinotify.WatchManager()
        wm.add_watch(def_location, pyinotify.IN_MODIFY)
        notifier = pyinotify.Notifier(wm, timeout=15*60*1000)
        notifier.loop(callback=lambda n: (commands.call_cmd('reset'),
                                          commands.call_cmd(args.view)))
    else:
        commands.call_cmd('reset')
        commands.call_cmd(args.view)
        while True:
            try:
                s = prompt_input(session, ctx)
                commands.call_cmd(s)
                con.commit()
            except AssertionError:
                print("Assertion not satisfied, cancelling command.")

            commands.call_cmd('reset')
            commands.call_cmd(args.view)
else:
    while True:
        s = prompt_input(session, ctx)
        try:
            commands.call_cmd(s)
            con.commit()
        except AssertionError:
            print("Assertion not satisfied, cancelling command.")
        except SystemExit:
            if len(s.split(' ')) == 1:
                quit()
