from prompt_toolkit import print_formatted_text as print
from prompt_toolkit import prompt, PromptSession
import sqlite3
#import dateutil.parser

import commands


con = sqlite3.connect("tasks.db")
con.row_factory = sqlite3.Row
cur = con.cursor()

commands.load_commands(cur)
session = PromptSession()

while True:
    commands.reload_autocomplete(cur)
    s = session.prompt("> ", completer=commands.completer).strip()
    clist = s.split(' ', 1)
    command = clist[0]

    aliases = {'dep': 'depends', 'scr': 'scry'}
    command = aliases.get(command, command)

    try:
        if command in ['exit', 'quit', 'q']:
            break
        elif command == '':
            continue
        elif command in ['cat', 'scry', 'bump', 'add', 'depends']:
            commands.call_cmd(cur, command, clist[1:])
            con.commit()
        elif command in ['tag']:
            commands.call_cmd(cur, command, clist[1].split(' '))
            con.commit()
        elif command in ['due', 'start', 'repeat', 'rename', 'redef']:
            commands.call_cmd(cur, command, clist[1].split(' ', 1))
            con.commit()
        else:
            if len(clist) == 1:
                tail = []
            else:
                tail = clist[1].split(' ')
            commands.call_cmd(cur, command, tail)
            con.commit()
    except AssertionError:
        print("Assertion not satisfied, cancelling command.")
