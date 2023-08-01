import dateutil.parser
from datetime import datetime
import parsedatetime as pdt
import re


def stringify(task, fullpath=False):
    ctx = task.ctx
    middle = 'x' if task.status else ' '
    desc = task.desc
    if fullpath:
        desc = task.get_rel_path()
    start_str = ""
    due_str = ""
    if task.status == None:
        if task.start != None:
            start_str = get_start_text(task.start)
            if not (start_str.endswith("ago") or start_str.endswith('yesterday')):
                start_str = ' <ansiblue>(' + start_str + ')</ansiblue>'
            else:
                start_str = ''
        if start_str == "" and task.due != None:
            due_str = get_due_text(task.due)
            if due_str.endswith("ago") or due_str.endswith('yesterday'):
                due_str = ' <ansired>(' + due_str + ')</ansired>'
            else:
                due_str = ' <ansigreen>(' + due_str + ')</ansigreen>'
    time_str = start_str + due_str

    tags_str = ' <ansiyellow>' + ' '.join(['#'+i for i in task.tags if i not in ['', 'group', 'collapse']]) + '</ansiyellow>'

    suffix = ''
    if task.has_tag('collapse') and len(task.get_pending_children()) > 0:
        suffix = " <ansigray>(collapsed)</ansigray>"

    desc = desc.replace('&', 'amp;')
    desc = desc.replace('<', '&lt;')
    desc = desc.replace('>', '&gt;')
    if task.has_tag('group'):
        return '- ' + desc + time_str + tags_str + suffix
    else:
        return '- ['+middle+'] ' + desc + time_str + tags_str + suffix


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

