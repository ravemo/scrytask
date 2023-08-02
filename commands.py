from prompt_toolkit.completion import NestedCompleter
import parsedatetime as pdt
import argparse
import os

from display import *
from task import *
from util import *


def cmd_add(ctx, args):
    task = Task(ctx, parse_new_task(ctx, ' '.join(args.details)))
    print(task)
    ctx.cur.execute("INSERT INTO tasks (uuid, parent, desc) values (?, ?, ?)", (task.uuid, task.parent, task.desc))
    task.write_str('start', task.start)
    task.write_str('due', task.due)
    task.write_str('repeat', task.repeat)
    task.write_str('tags', task.get_tags_str())
    task.write_str('depends', task.get_depends_str())
    task.write_str('created', str(datetime.now()))


def cmd_rename(ctx, args):
    new_task = parse_new_task(ctx, ' '.join(args.details))
    get_task(ctx, args.uuid).write_str('desc', new_task['desc'])


def cmd_done(ctx, args):
    cal = pdt.Calendar()
    task = get_task(ctx, str_to_uuid(ctx, ' '.join(args.id)))
    repeat = task.repeat
    if repeat != None:
        print(repeat)
        repeat = repeat.removeprefix('every ')
        if not (repeat[0:2] == 'a ' or repeat[0].isdigit()):
            repeat = '1 '+repeat
        new_start = None
        if task.start != None:
            new_start = cal.parseDT('in '+repeat, task.start)[0]
        if task.due != None:
            new_due = cal.parseDT('in '+repeat, task.due)[0]
        if new_start != None:
            print('Reset "' + task.desc + '" to ' + str(new_start)+" ~ "+str(new_due))
            task.write_str('start', str(new_start))
        else:
            print('Reset "' + task.desc + '" to ' + str(new_due))
        task.write_str('due', str(new_due))
    else:
        print('Completed "' + task.desc + '".')
        task.write_str('status', str(datetime.now()))


def cmd_undone(ctx, args):
    task = get_task(ctx, str_to_uuid(ctx, ' '.join(args.id)))
    task.write_str('status', None)


def _start_due_repeat_common(ctx, args, command):
    cal = pdt.Calendar()
    task = get_task(ctx, args.uuid)
    details = ' '.join(args.details)
    if command == 'start' or command == 'due':
        new_val = None if details == '' else cal.parseDT(details, datetime.now())[0]
        print("set new "+command+" to", str(new_val))
        task.write_str(command, str(new_val))
    else:
        new_repeat = None if details == '' else details
        task.write_str('repeat', args.details)

def cmd_start(ctx, args):
    _start_due_repeat_common(ctx, args, 'start')
def cmd_due(ctx, args):
    _start_due_repeat_common(ctx, args, 'due')
def cmd_repeat(ctx, args):
    _start_due_repeat_common(ctx, args, 'repeat')


def cmd_rm(ctx, args):
    recursive = False
    uuid = str_to_uuid(ctx, ' '.join(args.id))
    task = get_task(ctx, uuid)
    if args.r:
        tasks = ctx.cur.execute("SELECT uuid FROM tasks WHERE parent = ?", (uuid,)).fetchall()
        tasks = [Task(ctx, dict(i)) for i in tasks]
        exec_recursively(task, tasks, 0, remove, {'ctx': ctx}, False)
    else:
        if len(ctx.cur.execute("SELECT uuid FROM tasks WHERE parent = ?", (uuid,)).fetchall()) > 0:
            print("Can't remove task with children. Use -r for recursive removal.")
        else:
            remove(task, None, None, {'ctx': ctx})


def cmd_info(ctx, args):
    print(get_task(ctx, str_to_uuid(ctx, ' '.join(args.id))))


def cmd_mv(ctx, args):
    task = get_task(ctx, args.uuid)
    dst_uuid = str_to_uuid(ctx, ' '.join(args.dst))
    task.write_int('parent', dst_uuid)
    print("Moving task '"+task.desc+"' to '"+get_task(ctx, dst_uuid).desc+"'")


def _list_tree_common(ctx, args, command):
    cal = pdt.Calendar()
    #os.system('clear')

    sort_filters = []
    if args.done_after == None:
        sort_filters.append(lambda i: (i.status != None))
    else:
        sort_filters.append(lambda i: not i.has_finished_after(dateutil.parser.parse(args.done_after)))

    sort_filters.append(lambda i: not i.has_started(cal.parseDT('in 24 hours', datetime.now())[0]))

    sort_filters.append(lambda i: (True in [i.has_tag(j) for j in args.exclude_tags]))
    if args.include_tags != None:
        sort_filters.append(lambda i: (True not in [i.has_tag(j) for j in args.include_tags]))

    filters = sort_filters

    if args.blocked:
        sort_filters.append(lambda i: not i.is_dependent())
    else:
        sort_filters.append(lambda i: i.has_pending_dependency())

    if args.leaf:
        sort_filters.append(lambda i: len(i.get_pending_children()) > 0)

    if command != 'tree':
        sort_filters += [lambda i: i.has_tag('group')]
    if args.all:
        filters = []
    elif args.due:
        filters = sort_filters + [lambda i: i.get_earliest_due() == None]
    else:
        filters = sort_filters

    limit = None if args.no_limit else args.n
    if args.id == []:
        root = ctx.get_working_uuid()
    else:
        root = str_to_uuid(ctx, ' '.join(args.id))

    # Temporarily change working task to root
    last_wrktsk = ctx.get_working_uuid()
    ctx.working_task = get_task(ctx, root)

    data = list(ctx.cur.execute('select * from tasks').fetchall())
    tasks = [Task(ctx, dict(i)) for i in data]
    filtered = [i for i in tasks if i.is_descendant(root)]


    if command == 'tree':
        if root != None:
            print_tree(filtered, sort_filters, filters, get_task(ctx, root), limit=limit)
        else:
            print_tree(filtered, sort_filters, filters, Task(ctx, {}), limit=limit)
    else:
        filtered = [i for i in filtered if not i.is_filtered(filters)]
        sort_tasks(filtered, sort_filters)
        if limit != None:
            remaining = limit
            stop_idx = limit
            for k, i in enumerate(filtered):
                if i.get_earliest_due() != None or not i.has_started(datetime.now()):
                    continue
                remaining -= 1
                if remaining == 0:
                    stop_idx = k+1

            filtered = filtered[:stop_idx]
        for i in filtered:
            justw = max([len(str(i.uuid)) for i in filtered])
            print(HTML(str(i.uuid).rjust(justw) + ' | ' + stringify(i, True, justw+3)))
    ctx.working_task = get_task(ctx, last_wrktsk)

def cmd_list(ctx, args):
    _list_tree_common(ctx, args, 'list')
def cmd_tree(ctx, args):
    _list_tree_common(ctx, args, 'tree')


def cmd_depends(ctx, args):
    get_task(ctx, args.dependent).add_dependency(args.dependency[0])

    for i in range(1, len(args.dependency)):
        get_task(ctx, args.dependency[i-1]).add_dependency(args.dependency[i])


def cmd_tag(ctx, args):
    if args.clear:
        ctx.cur.execute("UPDATE tasks SET tags = NULL WHERE uuid = {}".format(args.uuid)) 
        return
    to_add = [i.replace('#', '').strip() for i in args.add]
    to_remove = [i.replace('#', '').strip() for i in args.exclude]
    to_add = [i for i in to_add if i != '']
    to_remove = [i for i in to_remove if i != '']
    get_task(ctx, args.uuid).add_tags(to_add)
    get_task(ctx, args.uuid).remove_tags(to_remove)


def _scry_bump_common(ctx, args, which):
    uuid = str_to_uuid(ctx, ' '.join(args.id))
    task = get_task(ctx, uuid)
    cond = ['status IS NULL', 'gauge IS NOT NULL', f'uuid != {uuid}']
    if args.local:
        if task.parent == None:
            cond.append('parent IS NULL')
        else:
            cond.append(f'parent = {task.parent}')

    cond = ' AND '.join(cond)
    gauges = [i[0] for i in ctx.cur.execute('SELECT gauge FROM tasks WHERE ' + cond)]
    add = 1 if which == 'scry' else -1
    ref = 0
    if len(gauges) > 0:
        ref = max(gauges) if which == 'scry' else min(gauges)
    task.update_gauge(ref + add)

    if args.local:
        # Keep minimum and maximum gauge of its siblings constant
        ctx.cur.execute(f'UPDATE tasks SET gauge = gauge - {add} WHERE ' + cond)
    elif len(gauges) > 0:
        # Make the minimum gauge be 1 so that every new task is added to the top
        ctx.cur.execute(f'UPDATE tasks SET gauge = gauge - {min(gauges)} + 1 WHERE ' + cond)


def cmd_scry(ctx, args):
    _scry_bump_common(ctx, args, 'scry')

def cmd_bump(ctx, args):
    _scry_bump_common(ctx, args, 'bump')


def cmd_cd(ctx, args):
    joined = ' '.join(args.id)
    if joined == '/':
        ctx.working_task = None
    elif joined == '..':
        if ctx.working_task == None:
            return None
        ctx.working_task = ctx.working_task.get_parent()
    else:
        ctx.working_task = get_task(ctx, str_to_uuid(ctx, joined))


def cmd_grep(ctx, args):
    search = ' '.join(args.search)
    matches = ctx.cur.execute("SELECT * FROM tasks WHERE desc LIKE '%{}%' AND status IS NULL".format(search)).fetchall()
    matches = [Task(ctx, dict(i)) for i in matches]

    sort_tasks(matches, [])
    for i in matches:
        justw = max([len(str(i.uuid)) for i in matches])
        print(HTML(str(i.uuid).rjust(justw) + ' | ' + stringify(i, True)))


def cmd_defrag(ctx, _args):
    defrag(ctx)
    os.system('clear')


def cmd_reset(_ctx, _args):
    os.system('clear')


def cmd_quit(_ctx, _args):
    quit()


all_cmds = set()
completer = None
def load_commands(cur):
    global all_cmds, parser, subparsers
    parser = argparse.ArgumentParser(prog='ttask')
    subparsers = parser.add_subparsers()
    all_cmds = {'add',
                'rename',
                'done',
                'undone',
                'start',
                'due',
                'repeat',
                'rm',
                'info',
                'mv',
                'tree',
                'list',
                'depends',
                'dep',
                'tag',
                'scry',
                'bump',
                'defrag',
                'reset',
                'cd',
                'grep',
                'quit',
                }

    for i in ['add']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('details', type=str, nargs='+')

    for i in ['rm']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('-r', action='store_true')
        subparser.add_argument('id', type=str, nargs='+')

    for i in ['mv']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('uuid', type=int)
        subparser.add_argument('dst', type=str, nargs='+')

    for i in ['list', 'tree']:
        default_limit = 10 if i == 'tree' else 5
        subparser = subparsers.add_parser(i)
        subparser.add_argument('-a', '--all', action='store_true')
        subparser.add_argument('--due', action='store_true')
        subparser.add_argument('--blocked', action='store_true')
        subparser.add_argument('--no-limit', action='store_true')
        subparser.add_argument('-l', '--leaf', action='store_true')
        subparser.add_argument('-x', '--exclude-tags', type=str, nargs='*', default=[])
        subparser.add_argument('--include-tags', type=str, nargs='*')
        subparser.add_argument('--done-after', type=str, action='store')
        subparser.add_argument('-n', type=int, action='store', default=default_limit)
        subparser.add_argument('id', type=str, nargs='*')

    for i in ['depends']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('dependent', type=int)
        subparser.add_argument('dependency', type=int, nargs='+')

    for i in ['rename', 'start', 'due', 'repeat']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('uuid', type=int)
        subparser.add_argument('details', type=str, nargs='*')

    for i in ['tag']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('uuid', type=int)
        subparser.add_argument('-c', '--clear', action='store_true')
        subparser.add_argument('-x', '--exclude', type=str, nargs='+', default=[])
        subparser.add_argument('add', type=str, nargs='*')

    for i in ['info', 'done', 'undone', 'cd']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('id', type=str, nargs='*')

    for i in ['scry', 'bump']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('-l', '--local', action='store_true')
        subparser.add_argument('id', type=str, nargs='*')

    for i in ['reset', 'defrag', 'quit']:
        subparser = subparsers.add_parser(i)

    for i in ['grep']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('search', type=str, nargs='*')



def reload_autocomplete(ctx):
    global completer
    data = ctx.cur.execute("SELECT c.desc FROM tasks c LEFT JOIN tasks p ON p.uuid = c.parent "+\
                           "WHERE c.status IS NULL AND (c.parent IS NULL OR p.tags NOT LIKE '% collapse %')").fetchall()

    task_descs = {i['desc']: None for i in data}
    with_auto = {'add', 'done', 'undone', 'rm', 'info', 'tree', 'list',
                 'scry', 'bump', 'cd'}
    completer = NestedCompleter.from_nested_dict(\
        {i: task_descs for i in with_auto} | \
        {i: None for i in all_cmds - with_auto})


def call_cmd(ctx, full_command):
    full_command = full_command.strip()
    if full_command == '':
        return

    aliases = {'dep': 'depends', 'scr': 'scry', 'exit': 'quit', 'q': 'quit'}
    argv = full_command.split(' ')
    argv[0] = aliases.get(argv[0], argv[0])
    cmd = argv[0]

    if cmd not in all_cmds:
        print("Unknown command:", '"'+cmd+'"')
        print(f"{argv=}")
        assert(0)
    args = parser.parse_args(argv)
    globals()['cmd_'+cmd](ctx, args)
