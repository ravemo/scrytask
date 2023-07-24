from prompt_toolkit.completion import NestedCompleter
import parsedatetime as pdt
import argparse
import os

from display import *
from task import *
from util import *


def cmd_add(cur, args):
    task = Task(cur, parse_new_task(cur, args.details))
    print(task)
    cur.execute("INSERT INTO tasks (uuid, parent, desc) values (?, ?, ?)", (task.uuid, task.parent, task.desc))
    task.write_str('start', task.start)
    task.write_str('due', task.due)
    task.write_str('repeat', task.repeat)
    task.write_str('tags', task.get_tags_str())
    task.write_str('created', str(datetime.now()))


def cmd_rename(cur, args):
    new_task = parse_new_task(cur, args.details)
    get_task(cur, args.uuid).write_str('desc', new_task['desc'])


def cmd_redef(cur, args):
    old_task = get_task(cur, args.uuid)
    new_task = parse_new_task(cur, args.details)
    old_task.write_str('desc', new_task['desc'])
    old_task.write_str('start', new_task['start'])
    old_task.write_str('due', new_task['due'])
    old_task.write_str('repeat', new_task['repeat'])


def cmd_done(cur, args):
    cal = pdt.Calendar()
    task = get_task(cur, str_to_uuid(cur, args.id))
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


def cmd_undone(cur, args):
    task = get_task(cur, str_to_uuid(cur, args.id))
    task.write_str('status', None)


def _start_due_repeat_common(cur, args, command):
    cal = pdt.Calendar()
    task = get_task(cur, args.uuid)
    if command == 'start' or command == 'due':
        new_val = None if args.details == None else cal.parseDT(args.details, datetime.now())[0]
        print("set new "+command+" to", str(new_val))
        task.write_str(command, new_val)
    else:
        new_repeat = None if args.details == None else args.details
        task.write_str('repeat', args.details)

def cmd_start(cur, args):
    _start_due_repeat_common(cur, args, 'start')
def cmd_due(cur, args):
    _start_due_repeat_common(cur, args, 'due')
def cmd_repeat(cur, args):
    _start_due_repeat_common(cur, args, 'repeat')


def cmd_rm(cur, args):
    recursive = False
    uuid = str_to_uuid(cur, ' '.join(args.arg))
    task = get_task(cur, uuid)
    if args.r:
        exec_recursively(task, tasks.values(), 0, remove, {'cur': cur}, False)
    else:
        if len(cur.execute("SELECT uuid FROM tasks WHERE parent = ?", (uuid,)).fetchall()) > 0:
            print("Can't remove task with children. Use -r for recursive removal.")
        else:
            remove(task, None, None, {'cur': cur})


def cmd_cat(cur, args):
    print(get_task(cur, str_to_uuid(cur, args.id)))


def cmd_mv(cur, args):
    task = get_task(cur, args.uuid)
    if args.dst == '..':
        task.write_int('parent', task.get_parent().parent)
    elif args.dst == '/':
        task.write_int('parent', None)
    else:
        task.write_int('parent', int(dst))


def _list_tree_common(cur, args, command):
    cal = pdt.Calendar()
    os.system('clear')

    sort_filters = []
    if args.done_after == None:
        sort_filters.append(lambda i: (i.status != None))
    else:
        sort_filters.append(lambda i: not i.has_finished_after(dateutil.parser.parse(args.done_after)))

    sort_filters.append(lambda i: not i.has_started(cal.parseDT('in 24 hours', datetime.now())[0]))

    filters = sort_filters

    if args.blocked:
        sort_filters.append(lambda i: not i.is_dependent())
    else:
        sort_filters.append(lambda i: i.has_pending_dependency())

    if command != 'tree':
        sort_filters += [lambda i: i.has_tag('group')]
    if args.all:
        filters = []
    elif args.due:
        filters = sort_filters + [lambda i: i.get_earliest_due() == None]
    else:
        filters = sort_filters

    limit = None if args.no_limit else args.n
    root = None if args.arg == [] else str_to_uuid(cur, ' '.join(args.arg))

    data = list(cur.execute('select * from tasks').fetchall())
    tasks = [Task(cur, dict(i)) for i in data]
    filtered = [i for i in tasks if i.is_descendant(root)]


    if command == 'tree':
        if root != None:
            print_tree(filtered, sort_filters, filters, get_task(cur, root), limit=limit)
        else:
            print_tree(filtered, sort_filters, filters, Task(cur, {}), limit=limit)
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
            print(HTML(str(i.uuid).ljust(justw) + ' | ' + stringify(i, True)))

def cmd_list(cur, args):
    _list_tree_common(cur, args, 'list')
def cmd_tree(cur, args):
    _list_tree_common(cur, args, 'tree')


def cmd_depends(cur, args):
    args = [int(i) for i in args.args.split(' on ')]
    for i in range(1, len(args)):
        get_task(cur, args[i-1]).add_dependency(args[i])


def cmd_tag(cur, args):
    if args.details == None:
        cur.execute("UPDATE tasks SET tags = NULL WHERE uuid = {}".format(args.uuid)) 
        return
    tag_list = [i.replace('#', '').strip() for i in args.details]
    tag_list = [i for i in tag_list if i != '']
    get_task(cur, args.uuid).add_tags(tag_list)


def _scry_bump_common(cur, args, which):
    uuid = str_to_uuid(cur, args.id)
    task = get_task(cur, uuid)
    if task.parent == None:
        gauges = list(cur.execute('SELECT gauge FROM tasks WHERE parent IS NULL AND uuid != {}'.format(uuid)).fetchall())
    else:
        gauges = list(cur.execute('SELECT gauge FROM tasks WHERE parent = {} AND uuid != {}'.format(task.parent, uuid)).fetchall())
    gauges = [i[0] if i[0] != None else 0 for i in gauges]
    if which == 'scry':
        max_gauges = max(gauges) if len(gauges) > 0 else 0
        task.update_gauge(max_gauges+1)
    else:
        min_gauges = min(gauges) if len(gauges) > 0 else 0
        task.update_gauge(min_gauges-1)

def cmd_scry(cur, args):
    _scry_bump_common(cur, args, 'scry')

def cmd_bump(cur, args):
    _scry_bump_common(cur, args, 'bump')

def cmd_defrag(cur, _args):
    defrag(cur)

def cmd_clear(cur, _args):
    os.system('clear')


all_cmds = set()
completer = None
def load_commands(cur):
    global all_cmds, parser, subparsers
    parser = argparse.ArgumentParser(prog='ttask')
    subparsers = parser.add_subparsers()
    all_cmds = {'add',
                'rename',
                'redef',
                'done',
                'undone',
                'start',
                'due',
                'repeat',
                'rm',
                'cat',
                'mv',
                'tree',
                'list',
                'depends',
                'dep',
                'tag',
                'scry',
                'bump',
                'defrag',
                'clear',
                }

    for i in ['add']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('details', type=str)

    for i in ['rm']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('-r', action='store_true')
        subparser.add_argument('arg', type=str, nargs='+')

    for i in ['mv']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('uuid', type=int)
        subparser.add_argument('dst', type=str)

    for i in ['list', 'tree']:
        default_limit = 10 if i == 'tree' else 5
        subparser = subparsers.add_parser(i)
        subparser.add_argument('--all', action='store_true')
        subparser.add_argument('--due', action='store_true')
        subparser.add_argument('--blocked', action='store_true')
        subparser.add_argument('--no-limit', action='store_true')
        subparser.add_argument('--done-after', type=str, action='store')
        subparser.add_argument('-n', type=int, action='store', default=default_limit)
        subparser.add_argument('arg', type=str, nargs='*')

    for i in ['depends']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('args', type=str)

    for i in ['rename', 'redef']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('uuid', type=int)
        subparser.add_argument('details', type=str)

    for i in ['start', 'due', 'repeat', 'tag']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('uuid', type=int)
        subparser.add_argument('details', type=str, nargs='?')

    for i in ['cat', 'scry', 'bump', 'done', 'undone']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('id', type=str)

    for i in ['clear', 'defrag']:
        subparser = subparsers.add_parser(i)
        subparser.add_argument('ignore', type=str, nargs='?')



def reload_autocomplete(cur):
    global completer
    data = cur.execute('select desc from tasks').fetchall()
    task_descs = {i['desc']: None for i in data}
    with_auto = {'add', 'done', 'undone', 'rm', 'cat', 'tree', 'list', 'scry', 'bump'}
    completer = NestedCompleter.from_nested_dict(\
        {i: task_descs for i in with_auto} | \
        {i: None for i in all_cmds - with_auto})


def call_cmd(cur, cmd, tail):
    if cmd not in all_cmds:
        print("Unknown command.")
        assert(0)
    args = parser.parse_args([cmd] + tail)
    globals()['cmd_'+cmd](cur, args)
