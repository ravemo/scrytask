from prompt_toolkit import print_formatted_text as print
from prompt_toolkit import prompt, HTML, PromptSession
from datetime import datetime
import parsedatetime as pdt
import sqlite3
import re

from display import *
from task import *

max_child_shown = 5

def sort_tasks(data, filters):
    data.sort(key=lambda x: (x.created == None,
                             x.created,
                             ),
              reverse=True)
    cal = pdt.Calendar()
    limit = cal.parseDT('in 2 days', datetime.now())[0]
    data.sort(key=lambda x: (x.status == None,
                             x.status,
                             (x.get_earliest_due(limit, filters=filters) == None),
                             (x.get_earliest_due(limit, filters=filters)),
                             (x.has_tag('group') and len(x.get_children(filters)) == 0),
                             x.gauge,
                            ))


def get_depth(tasks, task):
    depth = 0
    ct = task
    while ct['parent'] != None:
        depth += 1
        ct = tasks[ct['parent']]
    return depth;


def get_new_uuid(cur, neg=False):
    all_uuids = [i['uuid'] for i in cur.execute("SELECT uuid FROM tasks").fetchall()]
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
    if breadthfirst and task.uuid != None and depth >= 0: # cool hack
        func(task, tasks, depth, args)
        if args.get('limit', [None])[0] != None:
            args['limit'][0] -= 1

    filters = args.get('filters', [])

    children = task.get_children(filters)
    if 'filters' in args:
        children = [i for i in children if not i.is_filtered(args['filters'])]
    hidden = 0
    sort_tasks(children, args.get('sort_filters', []))

    # Hide children
    if depth >= 0 and args.get('limit_children', None) != None and len(children) > 6:
        hidden = len(children) - len(children[:args['limit_children']])
        children = children[:args['limit_children']]

    # Recursive part
    if args.get('hidden_function', None) == None or not task.has_tag('collapse'):
        for i in children:
            exec_recursively(i, tasks, depth+1, func, args)

    if hidden > 0 and args.get('hidden_function', None) != None:
        args['hidden_function'](hidden, depth+1)

    # Apply functions depth-first if applicable
    if not breadthfirst and task.uuid != None and depth >= 0:
        func(task, tasks, depth)
        if args.get('limit', [None])[0] != None:
            args['limit'][0] -= 1

was_separated = False
def print_tree_line(task, tasks, depth, args = None):
    justw = max([len(str(i.uuid)) for i in tasks])
    filters = args.get('filters', [])

    global was_separated
    prev_sep = was_separated
    if depth == 0:
        if task.has_tag('group') or len(task.get_descendants()) >= 2:
            print(' '*justw + ' | ')
            was_separated = True
        else:
            was_separated = False

    if prev_sep and not was_separated:
        print(' '*justw + ' | ')

    print(HTML(str(task.uuid).rjust(justw) + ' | ' + ' '*4*depth + stringify(task)))


def print_tree(tasks, sort_filters, filters, root_task={'uuid': None}, limit=None):
    justw = max([len(str(i.uuid)) for i in tasks])
    exec_recursively(root_task, tasks, -1, print_tree_line,
                     {'limit_children': 5, 'sort_filters': sort_filters,
                      'hidden_function': lambda h, d: print(' '*justw + ' | ' + ' '*4*d + str(h) + " tasks hidden."),
                      'limit': [limit],
                      'filters': filters})


def update_uuid(task, new_uuid):
    old_uuid = task.uuid
    task.write_int('uuid', new_uuid)
    cur.execute("UPDATE tasks SET parent = '{}' WHERE parent = {}".format(new_uuid, old_uuid)) 
    cur.execute("UPDATE tasks SET depends = replace(depends, ' {} ', ' {} ')".format(old_uuid, new_uuid)) 


def assign_uuid(task):
    new_uuid = get_new_uuid(task.status != None)
    update_uuid(task, new_uuid)

def remove(task, _tasks, _depth, args):
    print('Removing task', task)
    args['cur'].execute("UPDATE tasks SET depends = replace(depends, ' {} ', '  ')".format(task.uuid)) 
    args['cur'].execute("DELETE FROM tasks WHERE uuid = {}".format(task.uuid))


def defrag(cur):
    # strip all names if they have whitespaces for some reason
    cur.execute("UPDATE tasks SET desc = trim(desc)")

    tasks = [Task(cur, dict(i)) for i in cur.execute("SELECT * FROM tasks").fetchall()]
    uuids = [i.uuid for i in tasks]
    uuid_max = max(uuids)
    uuid_min = min(uuids)
    for i in tasks:
        k = i.uuid
        if k < 0:
            update_uuid(i, k+uuid_min-2) # So that we can rewrite the uuids later without conflicts
        else:
            update_uuid(i, k+uuid_max+1) # So that we can rewrite the uuids later without conflicts

    tasks = [Task(cur, dict(i)) for i in cur.execute("SELECT * FROM tasks").fetchall()]
    sort_filters = [
        (lambda i: (i.status != None)),
        (lambda i: not i.has_started(cal.parseDT('in 24 hours', now)[0])),
        (lambda i: i.has_pending_dependency()),
    ]
    sort_tasks(tasks, sort_filters)
    for i in tasks:
        assign_uuid(i)
    con.commit()


def split_esc(text, ch):
    return re.split(r'(?<!\\)'+ch, text)


def parse_new_task(cur, args):
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
    parent_uuid = None if len(splitted) == 1 else str_to_uuid(cur, '/'.join(splitted[:-1]))
    desc = splitted[-1].strip()

    print(desc)
    desc = desc.replace(r'\@', '@').replace(r'\/', '/').replace(r'\#', '#')
    task = {'uuid': get_new_uuid(cur), 'parent': parent_uuid, 'desc': desc,
            'start': start, 'due': due, 'repeat': repeat, 'tags': tags}
    return task


def fetch_task(cur, desc, parent=None):
    if parent != None:
        candidates = list(cur.execute("SELECT * FROM tasks WHERE desc='{}' AND parent={}".format(desc, parent)).fetchall())
    else:
        candidates = list(cur.execute("SELECT * FROM tasks WHERE desc='{}'".format(desc)).fetchall())
    if len(candidates) == 0:
        print("ERROR: No task with this name")
        assert(0)
    elif len(candidates) > 1:
        print("ERROR: Multiple tasks with same name; couldn't decide on correct task.")
        assert(0)
    else:
        return candidates[0]['uuid']

def fetch_pending_task(cur, desc, parent=None):
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


def str_to_uuid(cur, s, pending_only=True):
    # TODO: Handle cases where there can have two tasks with the same parent
    splitted = split_esc(s, '/')
    if len(splitted) == 1:
        if splitted[0].replace('-', '').isdigit():
            return int(splitted[0])
        else:
            if pending_only:
                return fetch_pending_task(cur, splitted[0])
            else:
                return fetch_task(cur, splitted[0])
    else:
        parent_uuid = str_to_uuid(cur, '/'.join(splitted[:-1]))
        if pending_only:
            return fetch_pending_task(cur, splitted[-1], parent_uuid)
        else:
            return fetch_task(cur, splitted[-1], parent_uuid)


def get_task(cur, uuid):
    return Task(cur, dict(cur.execute('SELECT * FROM tasks WHERE uuid={}'.format(uuid)).fetchone()))

