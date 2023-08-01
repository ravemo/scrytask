from prompt_toolkit import print_formatted_text as print
from prompt_toolkit import prompt, PromptSession
import sqlite3

import commands
import context


con = sqlite3.connect("tasks.db")
con.row_factory = sqlite3.Row
cur = con.cursor()
ctx = context.Context(cur)

commands.load_commands(cur)
session = PromptSession()

while True:
    commands.reload_autocomplete(ctx)
    working_desc = '/' if ctx.working_task == None else working_task.desc
    if len(working_desc) > 12:
        working_desc = working_desc[:10]+'...'
    s = session.prompt("["+working_desc+"] > ", completer=commands.completer).strip()
    clist = s.split(' ', 1)
    command = clist[0]

    aliases = {'dep': 'depends', 'scr': 'scry'}
    command = aliases.get(command, command)

    try:
        if command in ['exit', 'quit', 'q']:
            break
        elif command == '':
            continue
        elif command in ['cat', 'add', 'depends']:
            commands.call_cmd(ctx, command, clist[1:])
            con.commit()
        elif command in ['tag']:
            commands.call_cmd(ctx, command, clist[1].split(' '))
            con.commit()
        elif command in ['due', 'start', 'repeat', 'rename', 'redef',
                         'scry', 'bump']:
            commands.call_cmd(ctx, command, clist[1].split(' ', 1))
            con.commit()
        else:
            if len(clist) == 1:
                tail = []
            else:
                tail = clist[1].split(' ')
            commands.call_cmd(ctx, command, tail)
            con.commit()
    except AssertionError:
        print("Assertion not satisfied, cancelling command.")
