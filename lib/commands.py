from prompt_toolkit.completion import NestedCompleter
import parsedatetime as pdt
import dateparser
import datetime
import argparse
import shlex
import os

from lib.display import *
from lib.task import *
from lib.util import *

def parse_id_list(cur, idlist):
    src_uuids = []
    for i in idlist:
        if i.replace('-', '').isdigit():
            src_uuids.append(int(i))
        else: 
            # It is possible some of the non-numbers are in the format x..y
            limits = i.split('..')
            if len(limits) == 2 and \
               False not in [j.replace('-', '').isdigit() for j in limits]:
                limits = [int(j) for j in limits]
                src_uuids += [j for j in range(limits[0], limits[1]+1)]
            else: # If it is not a number, consider them as a pattern matching.
                # Do a few substitutions to change the unix-like pattern
                # matching into SQLite pattern matching.
                pattern = i.replace("'", "''").replace('"', '""')
                pattern = pattern.replace('%', '\\%').replace('_', '\\_')
                pattern = pattern.replace('*', '%').replace('?', '_')

                src_uuids += [j['uuid'] for j in cur.execute(f"""SELECT uuid FROM tasks WHERE status IS NULL AND desc LIKE "{pattern}" ESCAPE '\\'""").fetchall()]
    return src_uuids


class CommandManager:
    def __init__(self, ctx, allowed_commands, nowrap):
        self.ctx = ctx
        self.parser = argparse.ArgumentParser(prog='scrytask')
        self.subparsers = self.parser.add_subparsers()
        self.whitelist = allowed_commands
        self.nowrap = nowrap
        self.all_cmds = {'add',
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
                         'requeue',
                         'bump',
                         'defrag',
                         'reset',
                         'cd',
                         'search',
                         'quit',
                         'time',
                         }

        for i in ['add']:
            subparser = self.subparsers.add_parser(i, description="Add a new task to the list.")
            subparser.add_argument('-b', '--bottom', action='store_true', help="Add the new task to the bottom of the list.")
            subparser.add_argument('details', type=str, nargs='+', help="Syntax: \n"+
            "{desc} [#{tag_1}] ... [#{tag_n}] [<- {dep}] [@ [{start}~] {due} [every {repeat}]]\n"+
            "Where anything inside [] is optional")

        for i in ['rm']:
            subparser = self.subparsers.add_parser(i, description="Remove task from the list permanently")
            subparser.add_argument('-r', action='store_true', help='Removes all subtasks recursively')
            subparser.add_argument('id', type=str, nargs='+', help='List of tasks to be removed')

        for i in ['mv']:
            subparser = self.subparsers.add_parser(i, description="Move tasks into another task as subtasks")
            subparser.add_argument('src', type=str, nargs='+', help='List of tasks to be moved')
            subparser.add_argument('dst', type=str, help='Task to be moved to')

        description = {'list': "Show a list of tasks. Shows only 5 non-due pending tasks by default.",
                       'tree': "Show a tree of tasks. Shows only 10 pending tasks by default."}
        for i in ['list', 'tree']:
            default_limit = 10 if i == 'tree' else 5
            subparser = self.subparsers.add_parser(i, description=description[i])
            subparser.add_argument('-a', '--all', action='store_true', help="Don't hide any task")
            subparser.add_argument('--due', action='store_true', help="Show only tasks that have due dates")
            subparser.add_argument('--no-due', action='store_true', help="Show only tasks that have no due dates")
            subparser.add_argument('--blocked', action='store_true', help="Show only tasks that have a pending dependency")
            subparser.add_argument('--no-limit', action='store_true', help="Don't limit number of tasks shown")
            subparser.add_argument('--no-uuid', action='store_true', help="Don't show uuid of tasks")
            subparser.add_argument('--no-boxes', action='store_true', help="Don't show completed/not completed boxes")
            subparser.add_argument('-l', '--leaf', action='store_true', help="Show only tasks with no subtasks")
            subparser.add_argument('-x', '--exclude-tags', type=str, nargs='*', default=[], help="Hide all tasks that contain any of the tags specified")
            subparser.add_argument('--include-tags', type=str, nargs='*', help="Hide all tasks that does not contain any of the tags specified")
            subparser.add_argument('--done-after', type=str, action='store', help="Show tasks that have finished after the date specified")
            subparser.add_argument('-n', type=int, action='store', default=default_limit, help="Set number of tasks to be shown. Due tasks are not counted towards this limit.")
            subparser.add_argument('id', type=str, nargs='*', help="Limits to subtasks of the task specified.")

        for i in ['depends']:
            subparser = self.subparsers.add_parser(i, description="Sets dependencies on tasks. Tasks with dependencies will be hidden until all its dependencies are completed.")
            subparser.add_argument('dependent', type=str, help="Task which will depend on the second argument.")
            subparser.add_argument('dependency', type=str, nargs='*', help="All tasks that the first task depends on.")
            subparser.add_argument('--clear', action='store_true', help="Remove all dependencies")
            subparser.add_argument('--chain', action='store_true', help="Make the tasks on each argument depend on the task of the next argument.")

        for i in ['rename', 'start', 'due', 'repeat', 'time']:
            description = {'rename': 'Rename task',
                           'start': 'Set start date',
                           'due': 'Set due date',
                           'repeat': 'Set repeat interval',
                           'time': 'Set time estimate to completion'}
            subparser = self.subparsers.add_parser(i, description=description[i])
            subparser.add_argument('id', type=str, help="Task to be modified")
            subparser.add_argument('details', type=str, nargs='*', help="Details of new parameters. Leave empty if you want to reset to default.")

        for i in ['tag']:
            subparser = self.subparsers.add_parser(i, description="Set tags")
            subparser.add_argument('id', type=str, help="Task to be modified")
            subparser.add_argument('-c', '--clear', action='store_true', help="Remove all existing tags on the task")
            subparser.add_argument('-x', '--exclude', type=str, nargs='+', default=[], help="Remove all tags specified")
            subparser.add_argument('add', type=str, nargs='*', help="Add all tags specified")

        for i in ['info', 'done', 'undone', 'cd']:
            description = {'info': "Shows all information about the task (uuid, description, start date, due date, repeat interval, dependencies, tags)",
                           'done': "Mark task as done",
                           'undone': "Mark task as not done",
                           'cd': "Navigate into a task"}
            subparser = self.subparsers.add_parser(i, description=description[i])
            subparser.add_argument('id', type=str, nargs='*', help="Target task")

        for i in ['requeue', 'bump']:
            description = {'requeue': "Move task into bottom of the list",
                           'bump': "Move task into top of the list"}
            subparser = self.subparsers.add_parser(i, description=description[i])
            subparser.add_argument('-l', '--local', action='store_true', help="DEPRECATED")
            subparser.add_argument('id', type=str, nargs='*', help="Target task")

        for i in ['reset', 'defrag', 'quit']:
            description = {'reset': 'Clear screen',
                           'defrag': 'Reorganizes UUIDs; gives smaller numbers to tasks closer to the top of the list',
                           'quit': 'Quit the program'}
            subparser = self.subparsers.add_parser(i, description=description[i])

        for i in ['search']:
            subparser = self.subparsers.add_parser(i, description='List all tasks containing a substring')
            subparser.add_argument('search', type=str, nargs='*', help='Substring to find')


    # ---------------------------------------------------------------------------
    # Command functions
    # ---------------------------------------------------------------------------
    def cmd_add(self, args):
        task = Task(self.ctx, parse_new_task(self.ctx, ' '.join(args.details)))
        family = self.ctx.get_descendants()
        cond = ['status IS NULL', 'gauge IS NOT NULL']
        cond.append('uuid in (' + ','.join([str(i.uuid) for i in family]) + ')')
        cond = ' AND '.join(cond)
        gauges = [i[0] for i in self.ctx.cur.execute('SELECT gauge FROM tasks WHERE ' + cond)]
        if args.bottom:
            gauge = max(gauges)+1 if len(gauges) > 0 else 1
        else:
            gauge = min(gauges)-1 if len(gauges) > 0 else None
        print(task)
        self.ctx.cur.execute("INSERT INTO tasks (uuid, parent, desc) values (?, ?, ?)", (task.uuid, task.parent, task.desc))
        task.write_str('start', task.start)
        task.write_str('due', task.due)
        task.write_str('repeat', task.repeat)
        task.write_str('tags', task.get_tags_str())
        task.write_str('depends', task.get_depends_str())
        task.write_str('created', str(datetime.now()))
        task.write_str('gauge', gauge)


    def cmd_rename(self, args):
        new_desc = parse_new_task(self.ctx, ' '.join(args.details))['desc']
        task = get_task(self.ctx, str_to_uuid(self.ctx, args.id))
        task.write_str('desc', new_desc)


    def cmd_done(self, args):
        cal = pdt.Calendar()
        task = get_task(self.ctx, str_to_uuid(self.ctx, ' '.join(args.id)))
        repeat = task.repeat
        if repeat is not None:
            print(repeat)
            repeat = repeat.removeprefix('every ')
            if not (repeat[0:2] == 'a ' or repeat[0].isdigit()):
                repeat = '1 '+repeat
            new_start = None
            if task.start is not None:
                new_start = cal.parseDT('in '+repeat, task.start)[0]
            if task.due is not None:
                new_due = cal.parseDT('in '+repeat, task.due)[0]
            if new_start is not None:
                print('Reset "' + task.desc + '" to ' + str(new_start)+" ~ "+str(new_due))
                task.write_str('start', str(new_start))
            else:
                print('Reset "' + task.desc + '" to ' + str(new_due))
            task.write_str('due', str(new_due))
        else:
            print('Completed "' + task.desc + '".')
            task.write_str('status', str(datetime.now()))


    def cmd_undone(self, args):
        task = get_task(self.ctx, str_to_uuid(self.ctx, ' '.join(args.id)))
        if task.repeat is None:
            task.write_str('status', None)
            return
        # if task repeats, we should set back the start and due date

        cal = pdt.Calendar()
        repeat = task.repeat.removeprefix('every ')
        if not (repeat[0:2] == 'a ' or repeat[0].isdigit()):
            repeat = '1 '+repeat
        new_start = None
        if task.start is not None:
            new_start = cal.parseDT(repeat+' ago', task.start)[0]
        if task.due is not None:
            new_due = cal.parseDT(repeat+' ago', task.due)[0]
        if new_start is not None:
            print('Reset "' + task.desc + '" to ' + str(new_start)+" ~ "+str(new_due))
            task.write_str('start', str(new_start))
        else:
            print('Reset "' + task.desc + '" to ' + str(new_due))
        task.write_str('due', str(new_due))


    def _start_due_repeat_common(self, args, command):
        cal = pdt.Calendar()
        task = get_task(self.ctx, str_to_uuid(self.ctx, args.id))
        details = ' '.join(args.details)
        if command == 'start' or command == 'due':
            new_val = None if details == '' else cal.parseDT(details, datetime.now())[0]
            print("set new "+command+" to", str(new_val))
            task.write_str(command, new_val)
        else:
            new_repeat = None if details == '' else details
            task.write_str('repeat', new_repeat)

    def cmd_start(self, args):
        self._start_due_repeat_common(args, 'start')
    def cmd_due(self, args):
        self._start_due_repeat_common(args, 'due')
    def cmd_repeat(self, args):
        self._start_due_repeat_common(args, 'repeat')


    def cmd_rm(self, args):
        recursive = False
        uuids = parse_id_list(self.ctx.cur, args.id)
        for uuid in uuids:
            task = get_task(self.ctx, uuid)
            if args.r:
                descendants = task.get_descendants()
                set_desc = set()
                for i in descendants:
                    if i.uuid in set_desc:
                        print("Duplicate detected, cancelling")
                        assert(0)
                    else:
                        set_desc.add(i.uuid)
                for i in descendants:
                    remove(self.ctx.cur, i)
                remove(self.ctx.cur, task)
            else:
                if len(self.ctx.cur.execute("SELECT uuid FROM tasks WHERE parent = ?", (uuid,)).fetchall()) > 0:
                    print("Can't remove task with children. Use -r for recursive removal.")
                else:
                    remove(self.ctx.cur, task)


    def cmd_info(self, args):
        task = get_task(self.ctx, str_to_uuid(self.ctx, ' '.join(args.id)))
        print(task)
        if task.parent is not None:
            print("parent:", task.parent)


    def cmd_mv(self, args):
        dst = str_to_uuid(self.ctx, args.dst)
        src_uuids = parse_id_list(self.ctx.cur, args.src)
        if dst in src_uuids:
            print("WARNING: Trying to move "+args.dst+" into itself. Removing it from src.")
            src_uuids.remove(dst)
            if len(src_uuids) == 0:
                print("WARNING: No tasks left to move. Ending operation.")
                return
        src_uuids_str = '(' + ','.join([str(i) for i in src_uuids]) + ')'
        if dst is None:
            self.ctx.cur.execute(f"UPDATE tasks SET parent = NULL WHERE uuid IN {src_uuids_str}")
            print("Moving tasks "+src_uuids_str+" to /'")
        else:
            self.ctx.cur.execute(f"UPDATE tasks SET parent={dst} WHERE uuid IN {src_uuids_str}")
            print("Moving tasks "+src_uuids_str+" to '"+get_task(self.ctx, dst).desc+"'")


    def _list_tree_common(self, args, command):
        cal = pdt.Calendar()
        start_limit = datetime.now() # TODO: Add argument to change this

        sort_filters = []
        if args.done_after is None:
            sort_filters.append(lambda i: (i.status is not None))
        else:
            sort_filters.append(lambda i: not i.has_finished_after(dateutil.parser.parse(args.done_after), command=='tree'))

        sort_filters.append(lambda i: not i.has_started(start_limit))

        sort_filters.append(lambda i: (True in [i.has_tag(j) for j in args.exclude_tags]))
        if args.include_tags is not None:
            sort_filters.append(lambda i: (True not in [i.has_tag(j) for j in args.include_tags]))

        filters = sort_filters

        if args.blocked:
            sort_filters.append(lambda i: not i.has_pending_dependency())
        else:
            sort_filters.append(lambda i: i.has_pending_dependency())

        if args.leaf:
            sort_filters.append(lambda i: len(i.get_pending_children()) > 0)

        if command != 'tree':
            sort_filters += [lambda i: i.has_tag('_group')]

        if args.all:
            filters = []
        elif args.due:
            filters = sort_filters + [lambda i: i.get_earliest_due() is None]
        elif args.no_due:
            filters = sort_filters + [lambda i: i.get_earliest_due() is not None]
        else:
            filters = sort_filters
        

        limit = None if args.no_limit else args.n
        if args.id == []:
            root = self.ctx.get_working_uuid()
        else:
            root = str_to_uuid(self.ctx, ' '.join(args.id))

        # Temporarily change working task to root
        last_wrktsk = self.ctx.get_working_uuid()
        self.ctx.working_task = get_task(self.ctx, root)

        data = list(self.ctx.cur.execute('select * from tasks').fetchall())
        tasks = [Task(self.ctx, dict(i)) for i in data]
        filtered = [i for i in tasks if i.is_descendant(root) and i.uuid != root]

        if command == 'tree':
            if root is not None:
                print_tree(filtered, sort_filters, filters, args, get_task(self.ctx, root), limit=limit, nowrap=self.nowrap)
            else:
                print_tree(filtered, sort_filters, filters, args, Task(self.ctx, {}), limit=limit, nowrap=self.nowrap)
        else:
            filtered = [i for i in filtered if not i.is_filtered(filters)]
            sort_tasks(filtered, sort_filters)
            if limit is not None:
                filtered = filtered[:limit]
            for i in filtered:
                if args.no_uuid:
                    wrap = -1 if self.nowrap else 0
                    print(HTML(stringify(i, True, wrap, not args.no_boxes)))
                else:
                    justw = max([len(str(i.uuid)) for i in filtered])
                    wrap = -1 if self.nowrap else justw+3
                    print(HTML(str(i.uuid).rjust(justw) + ' | ' + stringify(i, True, wrap, not args.no_boxes)))
        self.ctx.working_task = get_task(self.ctx, last_wrktsk)

    def cmd_list(self, args):
        self._list_tree_common(args, 'list')
    def cmd_tree(self, args):
        self._list_tree_common(args, 'tree')


    def cmd_depends(self, args):
        for i in args.dependency:
            if not i.isdigit():
                print("Error: '"+i+"' is not an uuid.")
                assert 0
        task = get_task(self.ctx, str_to_uuid(self.ctx, args.dependent))
        if args.clear:
            task.depends = []
            task.write_str('depends', None)

        if args.chain:
            chain = [args.dependent] + args.dependency
            for i in range(len(chain)-1):
                taski = get_task(self.ctx, str_to_uuid(self.ctx, chain[i]))
                taski.add_dependency(chain[i+1])
        else:
            for i in args.dependency:
                task.add_dependency(i)


    def cmd_tag(self, args):
        uuid = str_to_uuid(self.ctx, args.id)
        if args.clear:
            self.ctx.cur.execute("UPDATE tasks SET tags = NULL WHERE uuid = {}".format(uuid)) 
            return
        to_add = [i.replace('#', '').strip() for i in args.add]
        to_remove = [i.replace('#', '').strip() for i in args.exclude]
        to_add = [i for i in to_add if i != '']
        to_remove = [i for i in to_remove if i != '']
        task = get_task(self.ctx, uuid)
        task.add_tags(to_add)
        task.remove_tags(to_remove)
        print("New tags:", "'"+task.get_tags_str()+"'")


    def _requeue_bump_common(self, args, which):
        uuid = str_to_uuid(self.ctx, ' '.join(args.id))
        task = get_task(self.ctx, uuid)
        family = self.ctx.get_descendants()
        cond = ['status IS NULL', 'gauge IS NOT NULL', f'uuid != {uuid}']
        cond.append('uuid in (' + ','.join([str(i.uuid) for i in family]) + ')')

        cond = ' AND '.join(cond)
        gauges = [i[0] for i in self.ctx.cur.execute('SELECT gauge FROM tasks WHERE ' + cond)]
        add = 1 if which == 'requeue' else -1
        ref = 0
        if len(gauges) > 0:
            ref = max(gauges) if which == 'requeue' else min(gauges)
        task.update_gauge(ref + add)

        # Keep minimum and maximum gauge of its siblings constant
        self.ctx.cur.execute(f'UPDATE tasks SET gauge = gauge - {add} WHERE ' + cond)


    def cmd_requeue(self, args):
        self._requeue_bump_common(args, 'requeue')

    def cmd_bump(self, args):
        self._requeue_bump_common(args, 'bump')


    def cmd_cd(self, args):
        joined = ' '.join(args.id)
        if joined == '/':
            self.ctx.working_task = None
        elif joined == '..':
            if self.ctx.working_task is None:
                return None
            self.ctx.working_task = self.ctx.working_task.get_parent()
        else:
            self.ctx.working_task = get_task(self.ctx, str_to_uuid(self.ctx, joined))


    def cmd_search(self, args):
        search = ' '.join(args.search)
        matches = self.ctx.cur.execute("SELECT * FROM tasks WHERE desc LIKE '%{}%' AND status IS NULL".format(search)).fetchall()
        matches = [Task(self.ctx, dict(i)) for i in matches]

        sort_tasks(matches, [])
        for i in matches:
            justw = max([len(str(i.uuid)) for i in matches])
            print(HTML(str(i.uuid).rjust(justw) + ' | ' + stringify(i, True)))


    def cmd_defrag(self, _args):
        defrag(self.ctx)
        os.system('clear')


    def cmd_reset(self, _args):
        os.system('clear')


    def cmd_quit(self, _args):
        quit()

    def cmd_time(self, args):
        task = get_task(self.ctx, str_to_uuid(self.ctx, args.id))
        details = ' '.join(args.details)
        if details == '':
            new_val = None
        else:
            relative_base = datetime.now()
            new_val = int((relative_base - dateparser.parse(details, settings={'RELATIVE_BASE': relative_base})).total_seconds())
        print("set new time to", str(new_val), "seconds")
        task.write_int("time", new_val)


    def reload_autocomplete(self):
        data = self.ctx.cur.execute("SELECT c.desc FROM tasks c LEFT JOIN tasks p ON p.uuid = c.parent "+
                                    "WHERE c.status IS NULL AND (c.parent IS NULL OR instr(p.tags, ' _collapse ') == 0)").fetchall()

        task_descs = {i['desc']: None for i in data}
        with_auto = {'add', 'done', 'undone', 'rm', 'info', 'tree', 'list',
                     'requeue', 'bump', 'cd'}
        self.completer = NestedCompleter.from_nested_dict(\
            {i: task_descs for i in with_auto} | \
            {i: None for i in self.all_cmds - with_auto})


    def call_cmd(self, full_command):
        full_command = full_command.strip()
        if full_command == '':
            return

        aliases = {'dep': 'depends', 'req': 'requeue', 'q': 'quit'}
        argv = full_command.split(' ')
        argv[0] = aliases.get(argv[0], argv[0])
        cmd = argv[0]
        # The arguments in this condition takes only a single task as an argument,
        # so shlex parsing will be a problem if we type things like "can't"
        if cmd in {'add', 'info', 'done', 'cd', 'requeue', 'bump'}:
            argv[1:] = full_command.split(' ')[1:]
        else:
            # Since shlex will translate \/ into /, we have to escape the \ 
            # because it will be useful for us later to know when it was escaped
            full_command = full_command.replace(r'\/', r'\\/')
            argv[1:] = shlex.split(full_command)[1:]
        if self.whitelist is not None and cmd not in self.whitelist:
            print("Command not allowed:", cmd)
            assert(0)

        if cmd not in self.all_cmds:
            print("Unknown command:", '"'+cmd+'"')
            print(f"{argv=}")
            assert(0)
        args = self.parser.parse_args(argv)
        getattr(self, 'cmd_'+cmd)(args)
