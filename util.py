from prompt_toolkit import print_formatted_text as print
from prompt_toolkit import prompt, PromptSession
from datetime import datetime
import parsedatetime as pdt
import sqlite3
import re

from display import *
from task import *

max_child_shown = 5

def is_empty_group(task, filters):
    """Check if group has any non-group descendant"""
    if not task.has_tag('_group'):
        return False
    new_filters = filters + [lambda x: x.has_tag('_group')]
    return len(task.get_descendants(new_filters)) == 0


def sort_tasks(data, filters):
    data.sort(key=lambda x: (x.status is None,
                             x.status,
                             x.created is None,
                             x.created,
                             ),
              reverse=True)
    cal = pdt.Calendar()
    limit = cal.parseDT('in 2 days', datetime.now())[0]
    data.sort(key=lambda x: (x.status is not None,
                             (x.get_earliest_due(limit, filters=filters) is None),
                             (x.get_earliest_due(limit, filters=filters)),
                             is_empty_group(x, filters),
                             x.gauge,
                            ))


def get_new_uuid(cur, negative=False):
    """Returns smallest positive (or negative if negative=True) uuid that is not in use."""
    all_uuids = [i['uuid'] for i in cur.execute("SELECT uuid FROM tasks").fetchall()]
    if negative:
        for i in range(0, min(all_uuids)-2, -1):
            if i not in all_uuids:
                return i
    else:
        for i in range(max(all_uuids)+2):
            if i not in all_uuids:
                return i
    assert(False)



def exec_recursively(task, tasks, depth, func, **kwargs):
    # TODO Clean this function
    limit = kwargs.get('limit', [None])
    if limit[0] == 0:
        return

    # Apply functions breadth-first
    if task.uuid is not None and depth >= 0: # cool hack
        func(task, tasks, depth, kwargs)
        if limit[0] is not None:
            limit[0] -= 1

    filters = kwargs.get('filters', [])

    children = task.get_children(filters)
    if 'filters' in kwargs:
        children = [i for i in children if not i.is_filtered(kwargs['filters'])]
    hidden = 0
    sort_tasks(children, kwargs.get('sort_filters', []))

    # Only show limit_children children per task if limit_children is set
    limit_children = kwargs.get('limit_children', None)
    if depth >= 0 and limit_children is not None and len(children) > limit_children+1:
        hidden = len(children) - len(children[:limit_children])
        children = children[:limit_children]

    # Recursive part
    if depth == -1 or kwargs.get('hidden_function', None) is None or not task.has_tag('_collapse'):
        for i in children:
            exec_recursively(i, tasks, depth+1, func, **kwargs)

    if hidden > 0 and kwargs.get('hidden_function', None) is not None:
        kwargs['hidden_function'](hidden, depth+1)


def print_tree(tasks, sort_filters, filters, root_task={'uuid': None}, limit=None, nowrap=False):
    justw = max([len(str(i.uuid)) for i in tasks])
    global is_first
    is_first = True
    exec_recursively(root_task, tasks, -1, print_tree_line,
                     **{'limit_children': 5, 'sort_filters': sort_filters,
                        'hidden_function': lambda h, d: print(' '*justw + ' | ' + ' '*4*d + str(h) + " tasks hidden."),
                        'limit': [limit],
                        'filters': filters,
                        'nowrap': nowrap})


def assign_uuid(task):
    new_uuid = get_new_uuid(task.ctx.cur, task.status is not None)
    task.update_uuid(new_uuid)


def remove(cur, task):
    print('Removing task', task)
    cur.execute("UPDATE tasks SET depends = replace(depends, ' {} ', ' ')".format(task.uuid)) 
    cur.execute("DELETE FROM tasks WHERE uuid = {}".format(task.uuid))


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
        (lambda i: (i.status is not None)),
        (lambda i: not i.has_started(cal.parseDT('in 24 hours', datetime.now())[0])),
        (lambda i: i.has_pending_dependency()),
    ]
    sort_tasks(tasks, sort_filters)
    for i in tasks:
        assign_uuid(i)


def split_esc(text, ch, maxsplit=0):
    """Splits text by ch but ignoring all ch escaped with a backslash.
    Does not work if ch is a backslash."""
    return re.split(r'(?<!\\)'+ch, text, maxsplit)


def unscape(text, strings):
    for i in strings:
        text = text.replace(f'\\{i}', i)
    return text


def parse_new_task(ctx, args):
    """ Creates a dictionary from arguments, according to the following format:
    {desc} [#{tag_1}] ... [#{tag_n}] [<- {dep}] [@ [{start}~] {due} [every {repeat}]]
    {} describes variables, [] is optional.
    """
    clean = lambda x: x[0].strip() if x != [] else None
    cal = pdt.Calendar()
    dep_pattern = re.compile(r".* <- .*")
    path = None
    start = None
    due = None

    # TODO: Split first, interpret later
    timeinfo, start, repeat, dep, due = [], [], [], [], None
    taskinfo, *timeinfo = split_esc(args, '@', 1)
    desc_and_tags, *dep = split_esc(taskinfo, '<-', 1)

    if timeinfo != []:
        startdue, *repeat = timeinfo[0].strip().split('every')
        *start, due = startdue.strip().split('~')

    repeat = 'every ' + clean(repeat) if repeat != [] else None
    start = clean(start)

    if start != None:
        start = str(cal.parseDT(start, datetime.now())[0])
    if due != None:
        due = str(cal.parseDT(due, datetime.now())[0])

    dep = ' '.join([str(str_to_uuid(ctx, i.strip())) for i in dep])

    desc, *tags = split_esc(desc_and_tags, '#')
    tags = ' '.join([i.strip() for i in tags])
    
    # Adding './' before is a nice hack to add to working task by default
    *parent, desc = split_esc('./'+desc, '/')
    parent = '/'.join(parent)
    parent_uuid = str_to_uuid(ctx, parent)

    desc = unscape(desc.strip(), ['@', '/', '#', '<', '-'])
    task = {'uuid': get_new_uuid(ctx.cur), 'parent': parent_uuid, 'desc': desc,
            'start': start, 'due': due, 'repeat': repeat, 'tags': tags,
            'depends': dep}
    return task


def fetch_task(cur, desc, parent=None, cond=[]):
    """Return children of parent with corresponding desc satisfying conditions in cond."""
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
    """Get uuid of the path/description/uuid specified by s."""
    splitted = split_esc(s, '/')
    cur_uuid = ctx.get_working_uuid()
    for i in splitted:
        if i == '.':
            continue
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
    if uuid is None:
        return None
    matches = ctx.cur.execute('SELECT * FROM tasks WHERE uuid={}'.format(uuid)).fetchall()
    if len(matches) == 0:
        print("ERROR: No task with uuid "+str(uuid)+".")
        assert(0)
    else:
        return Task(ctx, dict(matches[0]))

