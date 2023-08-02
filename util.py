from prompt_toolkit import print_formatted_text as print
from prompt_toolkit import prompt, HTML, PromptSession
from datetime import datetime
import parsedatetime as pdt
import sqlite3
import re

from display import *
from task import *

max_child_shown = 5

def is_empty_group(task, filters):
    if not task.has_tag('group'):
        return False
    new_filters = filters + [lambda x: x.has_tag('group')]
    return len(task.get_descendants(new_filters)) == 0


def sort_tasks(data, filters):
    data.sort(key=lambda x: (x.status == None,
                             x.status,
                             x.created == None,
                             x.created,
                             ),
              reverse=True)
    cal = pdt.Calendar()
    limit = cal.parseDT('in 2 days', datetime.now())[0]
    data.sort(key=lambda x: (x.status != None,
                             (x.get_earliest_due(limit, filters=filters) == None),
                             (x.get_earliest_due(limit, filters=filters)),
                             is_empty_group(x, filters),
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
    if depth == -1 or args.get('hidden_function', None) == None or not task.has_tag('collapse'):
        for i in children:
            exec_recursively(i, tasks, depth+1, func, args)

    if hidden > 0 and args.get('hidden_function', None) != None:
        args['hidden_function'](hidden, depth+1)

    # Apply functions depth-first if applicable
    if not breadthfirst and task.uuid != None and depth >= 0:
        func(task, tasks, depth, args)
        if args.get('limit', [None])[0] != None:
            args['limit'][0] -= 1

was_separated = False
is_first = True
def print_tree_line(task, tasks, depth, args = None):
    justw = max([len(str(i.uuid)) for i in tasks])
    filters = args.get('filters', [])

    global was_separated, is_first
    prev_sep = was_separated
    if depth == 0:
        if task.has_tag('group') or len(task.get_descendants()) >= 2:
            if not is_first:
                print(' '*justw + ' | ')
            was_separated = True
        else:
            was_separated = False

    if prev_sep and not was_separated and not is_first:
        print(' '*justw + ' | ')

    print(HTML(str(task.uuid).rjust(justw) + ' | ' + ' '*4*depth + stringify(task, False, justw+3+4*depth)))
    is_first = False


def print_tree(tasks, sort_filters, filters, root_task={'uuid': None}, limit=None):
    justw = max([len(str(i.uuid)) for i in tasks])
    global is_first
    is_first = True
    exec_recursively(root_task, tasks, -1, print_tree_line,
                     {'limit_children': 5, 'sort_filters': sort_filters,
                      'hidden_function': lambda h, d: print(' '*justw + ' | ' + ' '*4*d + str(h) + " tasks hidden."),
                      'limit': [limit],
                      'filters': filters})


def assign_uuid(task):
    new_uuid = get_new_uuid(task.ctx.cur, task.status != None)
    task.update_uuid(new_uuid)

def remove(task, _tasks, _depth, args):
    print('Removing task', task)
    args['ctx'].cur.execute("UPDATE tasks SET depends = replace(depends, ' {} ', '  ')".format(task.uuid)) 
    args['ctx'].cur.execute("DELETE FROM tasks WHERE uuid = {}".format(task.uuid))


def defrag(ctx):
    cal = pdt.Calendar()
    # strip all names if they have whitespaces for some reason
    ctx.cur.execute("UPDATE tasks SET desc = trim(desc)")

    tasks = [Task(ctx, dict(i)) for i in ctx.cur.execute("SELECT * FROM tasks").fetchall()]
    uuids = [i.uuid for i in tasks]
    uuid_max = max(uuids)
    uuid_min = min(uuids)
    for i in tasks:
        k = i.uuid
        if k < 0:
            i.update_uuid(k+uuid_min-2) # So that we can rewrite the uuids later without conflicts
        else:
            i.update_uuid(k+uuid_max+1) # So that we can rewrite the uuids later without conflicts

    tasks = [Task(ctx, dict(i)) for i in ctx.cur.execute("SELECT * FROM tasks").fetchall()]
    sort_filters = [
        (lambda i: (i.status != None)),
        (lambda i: not i.has_started(cal.parseDT('in 24 hours', datetime.now())[0])),
        (lambda i: i.has_pending_dependency()),
    ]
    sort_tasks(tasks, sort_filters)
    for i in tasks:
        assign_uuid(i)


def split_esc(text, ch):
    return re.split(r'(?<!\\)'+ch, text)


def parse_new_task(ctx, args):
    cal = pdt.Calendar()
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
            start = str(cal.parseDT(start, datetime.now())[0])
        if due != None:
            due = str(cal.parseDT(due, datetime.now())[0])
        print('start =', start)
        print('due =', due)
        print('repeat =', repeat)
    else:
        path = args

    splitted = split_esc(path, '<-')
    path = splitted[0].strip()
    dep = None
    if len(splitted) > 1:
        dep = [str_to_uuid(ctx, splitted[1].strip())]

    splitted = split_esc(path, '#')
    tags = None
    if len(splitted) > 1:
        path, tags = splitted[0], splitted[1:]
        tags = [i.strip() for i in tags]
        tags = ', '.join(tags)
    
    splitted = split_esc(path, '/')
    if len(splitted) == 1:
        parent_uuid = ctx.get_working_uuid()
    else:
        parent_uuid = str_to_uuid(ctx, '/'.join(splitted[:-1]))
    desc = splitted[-1].strip()

    desc = desc.replace(r'\@', '@').replace(r'\/', '/').replace(r'\#', '#')
    desc = desc.replace(r'\<', '<').replace(r'\-', '-')
    task = {'uuid': get_new_uuid(ctx.cur), 'parent': parent_uuid, 'desc': desc,
            'start': start, 'due': due, 'repeat': repeat, 'tags': tags,
            'depends': dep}
    return task


def fetch_task(cur, desc, parent=None, cond=[]):
    formatted_desc = desc.replace('"', '""').replace("'", "''")
    cond.append("desc='{}'".format(formatted_desc))
    cond.append("parent " + (f"= {parent}" if parent else "IS NULL"))
    cond_str = " AND ".join(cond)

    candidates = list(cur.execute(f"SELECT uuid FROM tasks WHERE {cond_str}").fetchall())
    if len(candidates) == 0:
        print(f"ERROR: No task with the name '{desc}'")
        assert(0)
    if len(candidates) > 1:
        print(f"ERROR: Multiple tasks with the name '{desc}'")
        assert(0)
    return candidates[0]['uuid']


def str_to_uuid(ctx, s, pending_only=True):
    splitted = split_esc(s, '/')
    cur_uuid = ctx.get_working_uuid()
    for i in splitted:
        if i == '..':
            cur_uuid = get_task(ctx, cur_uuid).parent
        elif i == '/':
            cur_uuid = None
        elif i.replace('-', '').isdigit():
            cur_uuid = int(i)
            _ = get_task(ctx, cur_uuid) # check if exists
        else:
            cond = ['status IS NULL'] if pending_only else []
            cur_uuid = fetch_task(ctx.cur, i, cur_uuid, cond)
    return cur_uuid


def get_task(ctx, uuid):
    if uuid == None:
        return None
    matches = ctx.cur.execute('SELECT * FROM tasks WHERE uuid={}'.format(uuid)).fetchall()
    if len(matches) == 0:
        print("ERROR: No task with uuid "+str(uuid)+".")
        assert(0)
    else:
        return Task(ctx, dict(matches[0]))

