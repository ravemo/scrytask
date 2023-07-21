from prompt_toolkit import print_formatted_text as print
from prompt_toolkit import prompt, HTML, PromptSession
from prompt_toolkit.completion import NestedCompleter
import dateutil.parser
from datetime import datetime
import parsedatetime as pdt
import shutil
import sqlite3
import os
import re
import argparse

max_child_shown = 5

def stringify(task, tasks=None, fullpath=False):
    middle = 'x' if task['status'] else ' '
    desc = task['desc']
    if fullpath:
        desc = get_full_path(tasks, task)
    start_str = ""
    due_str = ""
    if task['status'] == None:
        if task['start'] != None:
            start_str = get_start_text(dateutil.parser.parse(task['start']))
            if not (start_str.endswith("ago") or start_str.endswith('yesterday')):
                start_str = ' <ansiblue>(' + start_str + ')</ansiblue>'
            else:
                start_str = ''
        if start_str == "" and task['due'] != None:
            due_str = get_due_text(dateutil.parser.parse(task['due']))
            if due_str.endswith("ago") or due_str.endswith('yesterday'):
                due_str = ' <ansired>(' + due_str + ')</ansired>'
            else:
                due_str = ' <ansigreen>(' + due_str + ')</ansigreen>'
    time_str = start_str + due_str

    tags_str = ''
    if task['tags'] != None:
        tags = [i.strip() for i in task['tags'].strip().split(' ') if i.strip() not in ['', 'group', 'collapse']]
        if len(tags) > 0:
            tags_str = '#'+' #'.join(tags)
            tags_str = ' <ansiyellow>'+tags_str+'</ansiyellow>'

    suffix = ''
    if has_tag(task, 'collapse') and len(get_pending_children_single(task)) > 0:
        suffix = " <ansigray>(collapsed)</ansigray>"

    if has_tag(task, 'group'):
        return '- ' + desc + time_str + tags_str + suffix
    else:
        return '- ['+middle+'] ' + desc + time_str + tags_str + suffix


def is_filtered(x, filters):
    return True in [i(x) for i in filters]

def sort_tasks(data, filters):
    data.sort(key=lambda x: (x['created'] == None,
                             x['created'],
                             ),
              reverse=True)
    data.sort(key=lambda x: (
                             (get_earliest_due(tasks, x, 'in 2 days', filters=filters) == None),
                             (get_earliest_due(tasks, x, 'in 2 days', filters=filters)),
                             (has_tag(x, 'group') and len(get_children(x, filters)) == 0),
                             (0 if x['gauge'] == None else x['gauge']),
                            ))


def get_rel_time_text(date):
    now = cal.parseDT('now')[0]
    delta = date - now
    seconds = 24*60*60-delta.seconds
    if delta.days == -1:
        hours = seconds//(60*60)
        hour_str = " hours" if hours != 1 else " hour"
        minutes = seconds//60 - hours*60
        min_str = " minutes" if minutes != 1 else " minute"
        if hours > 0:
            return str(hours) + hour_str + " and " + str(minutes) + min_str + " ago", True
        else:
            return str(minutes) + min_str + " ago", True
    if delta.days == -2:
        return "yesterday", True
    elif delta.days < -1:
        return str(-delta.days) + " days ago", True
    elif delta.days == 1:
        return "tomorrow", False
    elif delta.days > 1:
        return "in " + str(delta.days) + " days", False
    else: # in less than 1 day
        hours = delta.seconds//(60*60)
        hour_str = " hours" if hours > 1 else " hour"
        minutes = delta.seconds//60 - hours*60
        min_str = " minutes" if minutes > 1 else " minute"
        if hours > 0:
            return "in " + str(hours) + hour_str + " and " + str(minutes) + min_str, False
        else:
            return "in " + str(minutes) + min_str, False


def get_due_text(date):
    time_str, _ = get_rel_time_text(date)
    return "Due "+time_str


def get_start_text(date):
    time_str, past = get_rel_time_text(date)
    if past:
        return "Started "+time_str
    else:
        return "Starts "+time_str


def get_root_uid(tasks, task):
    ct = task
    while ct['parent'] != None:
        ct = tasks[ct['parent']]
    return ct['uuid'];


def get_full_path(tasks, task):
    path = task['desc']
    ct = task
    while ct['parent'] != None:
        ct = tasks[ct['parent']]
        path = ct['desc']+'/'+path
    return path;


def get_children(x, filters=[]):
    l = list(cur.execute('select * from tasks where parent = {}'.format(x['uuid'])).fetchall())
    return [i for i in l if not is_filtered(dict(i), filters)]

def get_pending_children_single(x):
    return list(cur.execute('select * from tasks where parent = {} and status IS NULL'.format(x['uuid'])).fetchall())

def get_pending_children(tasks, x):
    return [i for i in tasks if i['parent'] == x['uuid'] and i['status'] == None]

def get_recursive_children(tasks, x):
    all_children = []
    exec_recursively(x, tasks, 0, lambda x, _a, _b, _c: all_children.append(x))
    all_children = [i for i in all_children if i != x]
    return all_children


def get_earliest_due(tasks, task, limit=None, filters=[]):
    children = [i for i in tasks.values() if i['parent'] == task['uuid'] and i['status'] == None]
    children = [i for i in children if not is_filtered(i, filters)]
    cur_due = dateutil.parser.parse(task['due']) if task['due'] != None else None
    cur_start = dateutil.parser.parse(task['start']) if task['start'] != None else None
    if len(children) == 0:
        if cur_start != None and cur_start >= now:
            return None
        if cur_due == None or limit != None and cur_due <= cal.parseDT(limit, now)[0]:
            return cur_due

    dues = [get_earliest_due(tasks, i, limit, filters) for i in children]
    dues = [i for i in dues if i != None]
    if cur_due != None:
        dues = [cur_due] + dues

    return min(dues) if len(dues) > 0 else None


def get_depth(tasks, task):
    depth = 0
    ct = task
    while ct['parent'] != None:
        depth += 1
        ct = tasks[ct['parent']]
    return depth;

def write_str(task, attr, val):
    if val == None:
        cur.execute("UPDATE tasks SET {} = NULL WHERE uuid = {}".format(attr, task['uuid'])) 
    else:
        cur.execute("UPDATE tasks SET {} = '{}' WHERE uuid = {}".format(attr, val, task['uuid'])) 

def write_int(task, attr, val):
    cur.execute("UPDATE tasks SET {} = {} WHERE uuid = {}".format(attr, 'NULL' if val == None else val, task['uuid'])) 

def get_new_uuid(neg=False):
    all_uuids = list(cur.execute("SELECT uuid FROM tasks").fetchall())
    all_uuids = [i['uuid'] for i in all_uuids]
    if neg:
        for i in range(0, min(all_uuids)-2, -1):
            if i not in all_uuids:
                return i
    else:
        for i in range(max(all_uuids)+2):
            if i not in all_uuids:
                return i
    assert(False)


def exec_recursively(task, tasks, depth, func, args={}, breadthfirst=True):
    if args.get('limit', [None])[0] == 0:
        return

    # Apply functions breadth-first if applicable
    if breadthfirst and task['uuid'] != None and depth >= 0: # cool hack
        func(task, tasks, depth, args)
        if args.get('limit', [None])[0] != None:
            args['limit'][0] -= 1

    children = [j for j in tasks if j['parent'] == task['uuid']]
    if 'filters' in args:
        children = [i for i in children if not is_filtered(i, args['filters'])]
    hidden = 0
    sort_tasks(children, args.get('sort_filters', []))

    # Hide children
    if depth >= 0 and args.get('limit_children', None) != None and len(children) > 6:
        hidden = len(children) - len(children[:args['limit_children']])
        children = children[:args['limit_children']]

    # Recursive part
    if args.get('hidden_function', None) == None or not has_tag(task, 'collapse'):
        for i in children:
            exec_recursively(i, tasks, depth+1, func, args)

    if hidden > 0 and args.get('hidden_function', None) != None:
        args['hidden_function'](hidden, depth+1)

    # Apply functions depth-first if applicable
    if not breadthfirst and task['uuid'] != None and depth >= 0:
        func(task, tasks, depth)
        if args.get('limit', [None])[0] != None:
            args['limit'][0] -= 1

was_separated = False
def print_tree_line(task, tasks, depth, _args = None):
    global was_separated
    prev_sep = was_separated
    if depth == 0:
        if (task['tags'] != None and 'group' in task['tags']) or \
           (len(get_recursive_children(tasks, task)) >= 2):
            print(' '*justw + ' | ')
            was_separated = True
        else:
            was_separated = False

    if prev_sep and not was_separated:
        print(' '*justw + ' | ')

    print(HTML(str(task['uuid']).rjust(justw) + ' | ' + ' '*4*depth + stringify(task)))

def print_tree(tasks, sort_filters, filters, root_task={'uuid': None}, limit=None):
    exec_recursively(root_task, tasks, -1, print_tree_line,
                     {'limit_children': 5, 'sort_filters': sort_filters,
                      'hidden_function': lambda h, d: print(' '*justw + ' | ' + ' '*4*d + str(h) + " tasks hidden."),
                      'limit': [limit],
                      'filters': filters})


def update_uuid(old_uuid, new_uuid):
    cur.execute("UPDATE tasks SET uuid = '{}' WHERE uuid = {}".format(new_uuid, old_uuid)) 
    cur.execute("UPDATE tasks SET parent = '{}' WHERE parent = {}".format(new_uuid, old_uuid)) 
    cur.execute("UPDATE tasks SET depends = replace(depends, '&{}&', '&{}&')".format(old_uuid, new_uuid)) 


def assign_uuid(task, _tasks, _depth, _args = None):
    new_uuid = get_new_uuid(task['status'] != None)
    update_uuid(task['uuid'], new_uuid)

def remove(task, _tasks = None, _depth = None, _args = None):
    print('Removing task', task)
    cur.execute("UPDATE tasks SET depends = replace(depends, '&{}&', '&&')".format(task['uuid'])) 
    cur.execute("DELETE FROM tasks WHERE uuid = {}".format(task['uuid']))


def defrag(tasks):
    cur.execute("UPDATE tasks SET desc = trim(desc)")
    uuid_max = max(tasks.keys())
    uuid_min = min(tasks.keys())
    for k, i in tasks.items():
        if k < 0:
            update_uuid(k, k+uuid_min-2) # So that we can rewrite the uuids later without conflicts
        else:
            update_uuid(k, k+uuid_max+1) # So that we can rewrite the uuids later without conflicts
    data = list(cur.execute('select * from tasks').fetchall())
    tasks.clear()
    tasks.update({i['uuid']: dict(i) for i in data})

    exec_recursively({'uuid': None}, tasks.values(), 0, assign_uuid)
    con.commit()

def is_dependent_recursive(task, tasks):
    d = has_pending_dependency(task, tasks)
    if d:
        return True
    else:
        return True in [is_dependent_recursive(i, tasks) for i in get_pending_children(tasks.values(), task)]

def has_pending_dependency(task, tasks):
    if task['depends'] == None:
        return False
    deps = [int(i.strip('&')) for i in task['depends'].split(' ')]
    # array of dependecies that have not been completed
    unsatis = [tasks[i]['status'] == None for i in deps]
    return True in unsatis


def is_descendant(child, root, tasks):
    if child['uuid'] == root or child['parent'] == root:
        return True
    elif child['parent'] == None:
        return False
    else:
        return is_descendant(tasks[child['parent']], root, tasks)


def split_esc(text, ch):
    return re.split(r'(?<!\\)'+ch, text)


def parse_new_task(tasks, args):
    path = None
    start = None
    due = None
    splitted = split_esc(args, '@')
    repeat = None # can't have != None without due != None
    if len(splitted) > 1:
        path, time = splitted
        path = path.strip()
        time = time.strip()
        if 'every' in time:
            repeat = 'every ' + time.split('every')[1].strip()
            time = time.split('every')[0].strip()
        if '~' in time:
            start, due = time.split('~')
            start = start.strip()
            due = due.strip()
        else:
            due = time
        if start != None:
            start = cal.parseDT(start, now)[0].isoformat().replace('T', ' ')
        if due != None:
            due = cal.parseDT(due, now)[0].isoformat().replace('T', ' ')
        print('start =', start)
        print('due =', due)
        print('repeat =', repeat)
    else:
        path = args

    splitted = split_esc(path, '#')
    tags = None
    if len(splitted) > 1:
        path, tags = splitted[0], splitted[1:]
        tags = [i.strip() for i in tags]
        tags = ', '.join(tags)
    
    splitted = split_esc(path, '/')
    parent_uuid = None if len(splitted) == 1 else str_to_uuid('/'.join(splitted[:-1]))
    desc = splitted[-1]

    print(desc)
    desc = desc.replace(r'\@', '@').replace(r'\/', '/').replace(r'\#', '#')
    task = {'uuid': get_new_uuid(), 'parent': parent_uuid, 'desc': desc,
            'start': start, 'due': due, 'repeat': repeat, 'tags': tags}
    return task


def has_tag(task, tag):
    if task.get('tags', None) == None:
        return False
    tags = [i.strip() for i in task['tags'].split(' ')]
    return tag in tags


def fetch_pending_task(desc, parent=None):
    if parent != None:
        candidates = list(cur.execute("SELECT * FROM tasks WHERE status IS NULL and desc='{}' AND parent={}".format(desc, parent)).fetchall())
    else:
        candidates = list(cur.execute("SELECT * FROM tasks WHERE status IS NULL and desc='{}'".format(desc)).fetchall())
    if len(candidates) == 0:
        print("ERROR: No task with this name")
        assert(0)
    elif len(candidates) > 1:
        print("ERROR: Multiple tasks with same name; couldn't decide on correct task.")
        assert(0)
    else:
        return candidates[0]['uuid']


def str_to_uuid(s):
    # TODO: Handle cases where there can have two tasks with the same parent
    splitted = split_esc(s, '/')
    if len(splitted) == 1:
        if splitted[0].isdigit():
            return int(splitted[0])
        else:
            return fetch_pending_task(splitted[0])
    else:
        parent_uuid = str_to_uuid('/'.join(splitted[:-1]))
        return fetch_pending_task(splitted[-1], parent_uuid)


def update_gauge(task, new_gauge):
    old_gauge = 0 if task['gauge'] == None else task['gauge']
    delta_gauge = new_gauge - old_gauge
    write_int(task, 'gauge', new_gauge)
    for i in get_children(task, []):
        old_gauge_i = 0 if i['gauge'] == None else i['gauge']
        update_gauge(i, old_gauge_i + delta_gauge)


def has_started(task, curtime):
    return (task['start'] == None or dateutil.parser.parse(task['start']) <= curtime)
    


con = sqlite3.connect("tasks.db")
con.row_factory = sqlite3.Row
cur = con.cursor()

session = PromptSession()

data = list(cur.execute('select * from tasks').fetchall())
tasks = {i['uuid']: dict(i) for i in data}

while True:
    task_descs = [i['desc'] for i in tasks.values()]
    task_descs = {i: None for i in task_descs}
    completer = NestedCompleter.from_nested_dict({
        'add': task_descs,
        'rename': None,
        'redef': None,
        'done': task_descs,
        'undone': task_descs,
        'setstart': None,
        'setdue': None,
        'setrepeat': None,
        'start': None,
        'due': None,
        'repeat': None,
        'rm': task_descs,
        'cat': task_descs,
        'mv': None,
        'tree': task_descs,
        'ls': task_descs,
        'list': task_descs,
        'depends': None,
        'dep': None,
        'tag': None,
        'scry': task_descs,
        'bump': task_descs,
        'defrag': None,
        'clear': None,
    })
    data = []
    tasks = {}
    s = session.prompt("> ", completer=completer).strip()
    clist = s.split(' ', 1)
    command = clist[0]

    cal = pdt.Calendar()
    now = datetime.now()

    # Load tasks
    data = list(cur.execute('select * from tasks').fetchall())
    tasks = {i['uuid']: dict(i) for i in data}


    try:
        if command in ['exit', 'quit', 'q']:
            break
        elif command == 'add':
            task = parse_new_task(tasks, clist[1])
            print(task)
            cur.execute("INSERT INTO tasks (uuid, parent, desc) values (?, ?, ?)", (task['uuid'], task['parent'], task['desc']))
            write_str(task, 'start', task['start'])
            write_str(task, 'due', task['due'])
            write_str(task, 'repeat', task['repeat'])
            write_str(task, 'tags', task['tags'])
            write_str(task, 'created', str(now))
            con.commit()
        elif command == 'rename':
            parser = argparse.ArgumentParser()
            parser.add_argument('uuid', type=int)
            parser.add_argument('new_args', type=str)
            args = parser.parse_args(clist[1].split(' ', 1))
            new_task = parse_new_task(tasks, args.new_args)
            write_str(tasks[int(args.uuid)], 'desc', new_task['desc'])
            con.commit()
        elif command == 'redef':
            parser = argparse.ArgumentParser()
            parser.add_argument('uuid', type=int)
            parser.add_argument('new_args', type=str)
            args = parser.parse_args(clist[1].split(' ', 1))
            old_task = tasks[args.uuid]
            new_task = parse_new_task(tasks, args.new_args)
            write_str(old_task, 'desc', new_task['desc'])
            write_str(old_task, 'start', new_task['start'])
            write_str(old_task, 'due', new_task['due'])
            write_str(old_task, 'repeat', new_task['repeat'])
            con.commit()
        elif command == 'done':
            task = tasks[str_to_uuid(clist[1])]
            repeat = task['repeat']
            if repeat != None:
                print(repeat)
                repeat = repeat.removeprefix('every ')
                if not (repeat[0:2] == 'a ' or repeat[0].isdigit()):
                    repeat = '1 '+repeat
                new_start = None
                if task['start'] != None:
                    new_start = cal.parseDT('in '+repeat, dateutil.parser.parse(task['start']))[0]
                new_due = cal.parseDT('in '+repeat, dateutil.parser.parse(task['due']))[0]
                if new_start != None:
                    print('Reset "' + task['desc'] + '" to ' + str(new_start)+" ~ "+str(new_due))
                    write_str(task, 'start', str(new_start))
                else:
                    print('Reset "' + task['desc'] + '" to ' + str(new_due))
                write_str(task, 'due', str(new_due))
            else:
                print('Completed "' + task['desc'] + '".')
                write_str(task, 'status', str(now))
            con.commit()
        elif command == 'undone':
            task = tasks[str_to_uuid(clist[1])]
            write_str(task, 'status', None)
            con.commit()
        elif command in ['setstart', 'start']:
            args = clist[1].split(' ', 1)
            task = tasks[int(args[0])]
            new_start = None if len(args) == 1 else cal.parseDT(args[1], now)[0]
            print("set new start to", str(new_start))
            write_str(task, 'start', new_start)
            con.commit()
        elif command in ['setdue', 'due']:
            args = clist[1].split(' ', 1)
            task = tasks[int(args[0])]
            new_due = None if len(args) == 1 else cal.parseDT(args[1], now)[0]
            print("set new due to", str(new_due))
            write_str(task, 'due', new_due)
            con.commit()
        elif command in ['setrepeat', 'repeat']:
            args = clist[1].split(' ', 1)
            task = tasks[int(args[0])]
            new_repeat = None if len(args) == 1 else args[1]
            write_str(task, 'repeat', args[1])
            con.commit()
        elif command == 'rm':
            parser = argparse.ArgumentParser()
            parser.add_argument('-r', action='store_true')
            parser.add_argument('arg', type=str, nargs='+')
            args = parser.parse_args(clist[1].split(' '))
            recursive = False
            uuid = str_to_uuid(' '.join(args.arg))
            if args.r:
                exec_recursively(tasks[uuid], tasks.values(), 0, remove, {}, False)
            else:
                if len(cur.execute("SELECT uuid FROM tasks WHERE parent = ?", (uuid,)).fetchall()) > 0:
                    print("Can't remove task with children. Use -r for recursive removal.")
                else:
                    remove(tasks[uuid])
            break
            con.commit()
        elif command == 'cat':
            print(tasks[str_to_uuid(clist[1])])
        elif command == 'mv':
            uuid = int(clist[1].split(' ')[0])
            arg = clist[1].split(' ')[1]
            if arg == '..':
                write_int(tasks[uuid], 'parent', tasks[tasks[uuid].parent].parent)
            elif arg == '/':
                write_int(tasks[uuid], 'parent', None)
            else:
                write_int(tasks[uuid], 'parent', int(arg))
            con.commit()
        elif command in ['list', 'ls', 'tree']:
            default_limit = 30 if command == 'tree' else 5
            os.system('clear')
            parser = argparse.ArgumentParser()
            parser.add_argument('--all', action='store_true')
            parser.add_argument('--due', action='store_true')
            parser.add_argument('--blocked', action='store_true')
            parser.add_argument('--nolimit', action='store_true')
            parser.add_argument('-n', type=int, action='store', default=default_limit)
            parser.add_argument('arg', type=str, nargs='*')
            args = parser.parse_args([] if len(clist) == 1 else clist[1].split(' '))

            justw = max([len(str(i)) for i in tasks.keys()])
            sort_filters = [
                (lambda i: (i['status'] != None)),
                (lambda i: not has_started(i, cal.parseDT('in 24 hours', now)[0])),
            ]

            filters = sort_filters

            if args.blocked:
                sort_filters.append(lambda i: not is_dependent_recursive(i, tasks))
            else:
                sort_filters.append(lambda i: has_pending_dependency(i, tasks))

            if command != 'tree':
                sort_filters += [lambda i: has_tag(i, 'group')]
            if args.all:
                filters = []
            elif args.due:
                filters = sort_filters + [lambda i: get_earliest_due(tasks, i) == None]
            else:
                filters = sort_filters

            limit = None if args.nolimit else args.n
            root = None if args.arg == [] else str_to_uuid(' '.join(args.arg))

            filtered = [i for i in tasks.values() if is_descendant(i, root, tasks)]

            if command == 'tree':
                if root != None:
                    print_tree(filtered, sort_filters, filters, tasks[root], limit=limit)
                else:
                    print_tree(filtered, sort_filters, filters, limit=limit)
            else:
                filtered = [i for i in filtered if not is_filtered(i, filters)]
                sort_tasks(filtered, sort_filters)
                if limit != None:
                    remaining = limit
                    stop_idx = limit
                    for k, i in enumerate(filtered):
                        if get_earliest_due(tasks, i) != None or not has_started(i, now):
                            continue
                        remaining -= 1
                        if remaining == 0:
                            stop_idx = k+1

                    filtered = filtered[:stop_idx]
                for i in filtered:
                    print(HTML(str(i['uuid']).ljust(justw) + ' | ' + stringify(i, tasks, True)))

        elif command in ['depends', 'dep']:
            args = [int(i) for i in clist[1].split(' on ')]
            for i in range(1, len(args)):
                old_depends = tasks[args[i-1]]['depends']
                if old_depends == None:
                    new_depends = '&'+str(args[i])+'&'
                else:
                    new_depends = old_depends + ' &'+str(args[i])+'&'
                cur.execute("UPDATE tasks SET depends = '{}' WHERE uuid = {}".format(new_depends, args[i-1])) 
            con.commit()

        elif command in ['tag']:
            if len(clist[1].split(' ')) == 1:
                uuid = int(clist[1])
                cur.execute("UPDATE tasks SET tags = NULL WHERE uuid = {}".format(uuid)) 
                con.commit()
                continue
            uuid, tag_list = [i for i in clist[1].split(' ', 1)]
            uuid = int(uuid)
            tag_list = tag_list.replace(',', '').split(' ')
            tag_list = [i.strip() for i in tag_list if i.strip() != '']
            old_tags = tasks[uuid]['tags']
            if old_tags == None:
                new_tags = ' ' + ' '.join(tag_list) + ' '
            else:
                if old_tags[-1] != ' ':
                    old_tags += ' '
                new_tags = old_tags + str(' '.join(tag_list)) + ' '
            print('old_tags =', old_tags, 'and new_tags =', new_tags)
            cur.execute("UPDATE tasks SET tags = '{}' WHERE uuid = {}".format(new_tags, uuid)) 
            con.commit()

        elif command in ['scry', 'scr', 'bump']:
            uuid = str_to_uuid(clist[1])
            parent = cur.execute('SELECT parent FROM tasks WHERE uuid = {}'.format(uuid)).fetchone()[0]
            if parent == None:
                gauges = list(cur.execute('SELECT gauge FROM tasks WHERE parent IS NULL AND uuid != {}'.format(uuid)).fetchall())
            else:
                gauges = list(cur.execute('SELECT gauge FROM tasks WHERE parent = {} AND uuid != {}'.format(parent, uuid)).fetchall())
            gauges = [i[0] if i[0] != None else 0 for i in gauges]

            if command in ['scry', 'scr']:
                if len(gauges) == 0:
                    update_gauge(tasks[uuid], 1)
                else:
                    update_gauge(tasks[uuid], max(gauges)+1)
            else:
                if len(gauges) == 0:
                    update_gauge(tasks[uuid], -1)
                else:
                    update_gauge(tasks[uuid], min(gauges)-1)
            con.commit()
        elif command == 'defrag':
            defrag(tasks)
        elif command == 'clear':
            os.system('clear')
        elif command == '':
            continue
        else:
            print("Unknown command.")
    except AssertionError:
        print("Assertion not satisfied, cancelling command.")
