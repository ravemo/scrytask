from prompt_toolkit import print_formatted_text as print
from prompt_toolkit import prompt, PromptSession
import sqlite3
import argparse
import pyinotify

import commands
import context


con = sqlite3.connect("tasks.db")
con.row_factory = sqlite3.Row
cur = con.cursor()
ctx = context.Context(cur)
commands.load_commands(cur)

parser = argparse.ArgumentParser(prog='ttask')
parser.add_argument('-i', '--interactive', action='store_true')
parser.add_argument('-v', '--view', type=str, nargs='?', default='')
parser.add_argument('-c', '--command', type=str, nargs='+', default=[])
args = parser.parse_args()

for i in args.command:
    try:
        commands.call_cmd(ctx, i)
        con.commit()
    except AssertionError:
        print("Assertion not satisfied, cancelling command.")

if args.view != '':
    if args.view == None:
        args.view = 'list'

    if not args.interactive:
        wm = pyinotify.WatchManager()
        wm.add_watch('tasks.db', pyinotify.IN_MODIFY)
        notifier = pyinotify.Notifier(wm, timeout=15*60*1000)
        notifier.loop(callback=lambda n: (commands.call_cmd(ctx, 'reset'),
                                          commands.call_cmd(ctx, args.view)))
    else:
        commands.call_cmd(ctx, 'reset')
        commands.call_cmd(ctx, args.view)
        while True:
            try:
                s = input('> ')
                commands.call_cmd(ctx, s)
                commands.call_cmd(ctx, 'reset')
                commands.call_cmd(ctx, args.view)
                con.commit()
            except AssertionError:
                print("Assertion not satisfied, cancelling command.")

else:
    session = PromptSession()

    while True:
        commands.reload_autocomplete(ctx)
        working_desc = '/' if ctx.working_task == None else ctx.working_task.desc
        if len(working_desc) > 20:
            working_desc = working_desc[:18]+'...'

        s = session.prompt("["+working_desc+"] > ", completer=commands.completer).strip()
        try:
            commands.call_cmd(ctx, s)
            con.commit()
        except AssertionError:
            print("Assertion not satisfied, cancelling command.")
