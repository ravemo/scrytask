import dateutil.parser
from datetime import datetime
import parsedatetime as pdt
import re
import shutil
import textwrap
from prompt_toolkit import print_formatted_text as print
from prompt_toolkit import HTML


def stringify(task, fullpath=False, start_x=0):
    """Returns markdown-like string giving all the important information about
    the task.

    Arguments
    ---------
    fullpath : bool
        Whether to print the full path or just the description.
    start_x : int
        Number of characters before the string will be printed.
        Used for word wrapping. -1 means no wrapping. """
    ctx = task.ctx
    desc = task.desc
    if fullpath:
        desc = task.get_rel_path()
    start_str = ""
    due_str = ""
    if task.status is None:
        if task.start is not None:
            start_str = get_start_text(task.start)
            if not (start_str.endswith("ago") or start_str.endswith('yesterday')):
                start_str = ' <ansiblue>(' + start_str + ')</ansiblue>'
            else:
                start_str = ''
        if start_str == "" and task.due is not None:
            due_str = get_due_text(task.due)
            if due_str.endswith("ago") or due_str.endswith('yesterday'):
                due_str = ' <ansired>(' + due_str + ')</ansired>'
            else:
                due_str = ' <ansigreen>(' + due_str + ')</ansigreen>'
    time_str = start_str + due_str

    tags_str = ' '.join(['#'+i for i in task.tags if i not in ['', '_group', '_collapse']])
    if tags_str != '':
        tags_str = ' <ansiyellow>' + tags_str + '</ansiyellow>'
    suffix = ''
    if task.has_tag('_collapse') and len(task.get_pending_children()) > 0:
        suffix = " <ansigray>(collapsed)</ansigray>"

    term_size = shutil.get_terminal_size((80, 20))
    middle = 'x' if task.status else ' '
    prefix = '- ' if task.has_tag('_group') else '- ['+middle+'] '
    if start_x > 0:
        start_x += len(prefix)
        desc = textwrap.wrap(desc, term_size[0] - start_x)
        desc = ('\n' + ' '*start_x).join(desc)

    desc = desc.replace('&', 'amp;')
    desc = desc.replace('<', '&lt;')
    desc = desc.replace('>', '&gt;')
    if task.has_pending_dependency():
        suffix += " <ansired>(blocked)</ansired>"
    return prefix + desc + time_str + tags_str + suffix


def get_due_text(date):
    time_str, _ = get_rel_time_text(date)
    return "Due "+time_str


def get_start_text(date):
    time_str, past = get_rel_time_text(date)
    if past:
        return "Started "+time_str
    else:
        return "Starts "+time_str


def get_rel_time_text(date):
    """Returns human-readable text of the time left until/passed since date."""
    now = datetime.now()
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


was_separated = False
is_first = True
def print_tree_line(task, tasks, depth, args = None):
    """Print a single line of a task tree."""
    justw = max([len(str(i.uuid)) for i in tasks])
    filters = args.get('filters', [])

    global was_separated, is_first
    prev_sep = was_separated
    if depth == 0:
        if task.has_tag('_group') or len(task.get_descendants()) >= 2:
            if not is_first:
                print(' '*justw + ' | ')
            was_separated = True
        else:
            was_separated = False

    if prev_sep and not was_separated and not is_first:
        print(' '*justw + ' | ')

    wrap = -1 if args['nowrap'] else justw + 3 + 4*depth 
    print(HTML(str(task.uuid).rjust(justw) + ' | ' + ' '*4*depth + stringify(task, False, wrap)))
    is_first = False
