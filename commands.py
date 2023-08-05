from prompt_toolkit.completion import NestedCompleter
import parsedatetime as pdt
import argparse
import os

from display import *
from task import *
from util import *


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
                         'scry',
                         'bump',
                         'defrag',
                         'reset',
                         'cd',
                         'grep',
                         'quit',
                         }

        for i in ['add']:
            subparser = self.subparsers.add_parser(i)
            subparser.add_argument('details', type=str, nargs='+')

        for i in ['rm']:
            subparser = self.subparsers.add_parser(i)
            subparser.add_argument('-r', action='store_true')
            subparser.add_argument('id', type=str, nargs='+')

        for i in ['mv']:
            subparser = self.subparsers.add_parser(i)
            subparser.add_argument('src', type=str, nargs='+')
            subparser.add_argument('dst', type=int)

        for i in ['list', 'tree']:
            default_limit = 10 if i == 'tree' else 5
            subparser = self.subparsers.add_parser(i)
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
            subparser = self.subparsers.add_parser(i)
            subparser.add_argument('dependent', type=int)
            subparser.add_argument('--clear', action='store_true')
            subparser.add_argument('dependency', type=int, nargs='*')

        for i in ['rename', 'start', 'due', 'repeat']:
            subparser = self.subparsers.add_parser(i)
            subparser.add_argument('uuid', type=int)
            subparser.add_argument('details', type=str, nargs='*')

        for i in ['tag']:
            subparser = self.subparsers.add_parser(i)
            subparser.add_argument('uuid', type=int)
            subparser.add_argument('-c', '--clear', action='store_true')
            subparser.add_argument('-x', '--exclude', type=str, nargs='+', default=[])
            subparser.add_argument('add', type=str, nargs='*')

        for i in ['info', 'done', 'undone', 'cd']:
            subparser = self.subparsers.add_parser(i)
            subparser.add_argument('id', type=str, nargs='*')

        for i in ['scry', 'bump']:
            subparser = self.subparsers.add_parser(i)
            subparser.add_argument('-l', '--local', action='store_true')
            subparser.add_argument('id', type=str, nargs='*')

        for i in ['reset', 'defrag', 'quit']:
            subparser = self.subparsers.add_parser(i)

        for i in ['grep']:
            subparser = self.subparsers.add_parser(i)
            subparser.add_argument('search', type=str, nargs='*')


    # ---------------------------------------------------------------------------
    # Command functions
    # ---------------------------------------------------------------------------
    def cmd_add(self, args):
        task = Task(self.ctx, parse_new_task(self.ctx, ' '.join(args.details)))
        print(task)
        self.ctx.cur.execute("INSERT INTO tasks (uuid, parent, desc) values (?, ?, ?)", (task.uuid, task.parent, task.desc))
        task.write_str('start', task.start)
        task.write_str('due', task.due)
        task.write_str('repeat', task.repeat)
        task.write_str('tags', task.get_tags_str())
        task.write_str('depends', task.get_depends_str())
        task.write_str('created', str(datetime.now()))


    def cmd_rename(self, args):
        new_task = parse_new_task(self.ctx, ' '.join(args.details))
        get_task(self.ctx, args.uuid).write_str('desc', new_task['desc'])


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
        task = get_task(self.ctx, args.uuid)
        details = ' '.join(args.details)
        if command == 'start' or command == 'due':
            new_val = None if details == '' else cal.parseDT(details, datetime.now())[0]
            print("set new "+command+" to", str(new_val))
            task.write_str(command, new_val)
        else:
            new_repeat = None if details == '' else details
            task.write_str('repeat', args.details)

    def cmd_start(self, args):
        self._start_due_repeat_common(args, 'start')
    def cmd_due(self, args):
        self._start_due_repeat_common(args, 'due')
    def cmd_repeat(self, args):
        self._start_due_repeat_common(args, 'repeat')


    def cmd_rm(self, args):
        recursive = False
        uuid = str_to_uuid(self.ctx, ' '.join(args.id))
        task = get_task(self.ctx, uuid)
        if args.r:
            tasks = self.ctx.cur.execute("SELECT uuid FROM tasks WHERE parent = ?", (uuid,)).fetchall()
            tasks = [Task(self.ctx, dict(i)) for i in tasks]
            exec_recursively(task, tasks, 0, remove, {'ctx': self.ctx}, False)
        else:
            if len(self.ctx.cur.execute("SELECT uuid FROM tasks WHERE parent = ?", (uuid,)).fetchall()) > 0:
                print("Can't remove task with children. Use -r for recursive removal.")
            else:
                remove(task, None, None, {'ctx': self.ctx})


    def cmd_info(self, args):
        print(get_task(self.ctx, str_to_uuid(self.ctx, ' '.join(args.id))))


    def cmd_mv(self, args):
        src_uuids = []
        if False not in [i.replace('-', '').isdigit() for i in args.src]:
            # If all strings are numbers, use all of them as uuids
            src_uuids = [int(i) for i in args.src]
        else: 
            # It is possible some of the non-numbers are in the format x..y
            range_test = [i.split('..') for i in args.src]
            flattened = [j for i in range_test for j in i]
            print(f"{flattened=}")
            if max([len(i) for i in range_test]) == 2 and \
               False not in [j.replace('-', '').isdigit() for j in flattened]:
                range_test = [[int(j) for j in i] for i in range_test]
                src_uuids = [i[0] for i in range_test if len(i) == 1]
                for i in range_test:
                    if len(i) == 2:
                        assert(i[1] > i[0])
                        src_uuids += [j for j in range(i[0], i[1]+1)]
            else: # If one of them is not a number, consider them as a pattern matching.
                # Do a few substitutions to change the unix-like pattern matching into
                # SQLite pattern matching.
                pattern = ' '.join(args.src).replace("'", "''")
                pattern = pattern.replace('%', '\\%').replace('_', '\\_')
                pattern = pattern.replace('*', '%').replace('?', '_')
                src_uuids = [i['uuid'] for i in self.ctx.cur.execute(f"""SELECT uuid FROM tasks WHERE desc LIKE "{pattern}" ESCAPE '\\'""").fetchall()]

        src_uuids_str = '(' + ','.join([str(i) for i in src_uuids]) + ')'
        self.ctx.cur.execute(f"UPDATE tasks SET parent={args.dst} WHERE uuid IN {src_uuids_str}")
        print("Moving tasks "+src_uuids_str+" to '"+get_task(self.ctx, args.dst).desc+"'")


    def _list_tree_common(self, args, command):
        cal = pdt.Calendar()

        sort_filters = []
        if args.done_after is None:
            sort_filters.append(lambda i: (i.status is not None))
        else:
            sort_filters.append(lambda i: not i.has_finished_after(dateutil.parser.parse(args.done_after), command=='tree'))

        sort_filters.append(lambda i: not i.has_started(cal.parseDT('in 24 hours', datetime.now())[0]))

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
            sort_filters += [lambda i: i.has_tag('group')]
        if args.all:
            filters = []
        elif args.due:
            filters = sort_filters + [lambda i: i.get_earliest_due() is None]
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
        filtered = [i for i in tasks if i.is_descendant(root)]

        if command == 'tree':
            if root is not None:
                print_tree(filtered, sort_filters, filters, get_task(self.ctx, root), limit=limit, nowrap=self.nowrap)
            else:
                print_tree(filtered, sort_filters, filters, Task(self.ctx, {}), limit=limit, nowrap=self.nowrap)
        else:
            filtered = [i for i in filtered if not i.is_filtered(filters)]
            sort_tasks(filtered, sort_filters)
            if limit is not None:
                remaining = limit
                stop_idx = limit
                for k, i in enumerate(filtered):
                    if i.get_earliest_due() is not None or not i.has_started(datetime.now()):
                        continue
                    remaining -= 1
                    if remaining == 0:
                        stop_idx = k+1

                filtered = filtered[:stop_idx]
            for i in filtered:
                justw = max([len(str(i.uuid)) for i in filtered])
                wrap = -1 if self.nowrap else justw+3
                print(HTML(str(i.uuid).rjust(justw) + ' | ' + stringify(i, True, wrap)))
        self.ctx.working_task = get_task(self.ctx, last_wrktsk)

    def cmd_list(self, args):
        self._list_tree_common(args, 'list')
    def cmd_tree(self, args):
        self._list_tree_common(args, 'tree')


    def cmd_depends(self, args):
        if args.clear:
            task = get_task(self.ctx, args.dependent)
            task.depends = []
            task.write_str('depends', None)

        for i in args.dependency:
            get_task(self.ctx, args.dependent).add_dependency(i)


    def cmd_tag(self, args):
        if args.clear:
            self.ctx.cur.execute("UPDATE tasks SET tags = NULL WHERE uuid = {}".format(args.uuid)) 
            return
        to_add = [i.replace('#', '').strip() for i in args.add]
        to_remove = [i.replace('#', '').strip() for i in args.exclude]
        to_add = [i for i in to_add if i != '']
        to_remove = [i for i in to_remove if i != '']
        task = get_task(self.ctx, args.uuid)
        task.add_tags(to_add)
        task.remove_tags(to_remove)
        print("New tags:", "'"+task.get_tags_str()+"'")


    def _scry_bump_common(self, args, which):
        uuid = str_to_uuid(self.ctx, ' '.join(args.id))
        task = get_task(self.ctx, uuid)
        cond = ['status IS NULL', 'gauge IS NOT NULL', f'uuid != {uuid}']
        if args.local:
            if task.parent is None:
                cond.append('parent IS NULL')
            else:
                cond.append(f'parent = {task.parent}')

        cond = ' AND '.join(cond)
        gauges = [i[0] for i in self.ctx.cur.execute('SELECT gauge FROM tasks WHERE ' + cond)]
        add = 1 if which == 'scry' else -1
        ref = 0
        if len(gauges) > 0:
            ref = max(gauges) if which == 'scry' else min(gauges)
        task.update_gauge(ref + add)

        if args.local:
            # Keep minimum and maximum gauge of its siblings constant
            self.ctx.cur.execute(f'UPDATE tasks SET gauge = gauge - {add} WHERE ' + cond)
        elif len(gauges) > 0:
            # Make the minimum gauge be 1 so that every new task is added to the top
            self.ctx.cur.execute(f'UPDATE tasks SET gauge = gauge - {min(gauges)} + 1 WHERE ' + cond)


    def cmd_scry(self, args):
        self._scry_bump_common(args, 'scry')

    def cmd_bump(self, args):
        self._scry_bump_common(args, 'bump')


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


    def cmd_grep(self, args):
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


    def reload_autocomplete(self):
        data = self.ctx.cur.execute("SELECT c.desc FROM tasks c LEFT JOIN tasks p ON p.uuid = c.parent "+\
                                    "WHERE c.status IS NULL AND (c.parent IS NULL OR p.tags NOT LIKE '% collapse %')").fetchall()

        task_descs = {i['desc']: None for i in data}
        with_auto = {'add', 'done', 'undone', 'rm', 'info', 'tree', 'list',
                     'scry', 'bump', 'cd'}
        self.completer = NestedCompleter.from_nested_dict(\
            {i: task_descs for i in with_auto} | \
            {i: None for i in self.all_cmds - with_auto})


    def call_cmd(self, full_command):
        full_command = full_command.strip()
        if full_command == '':
            return

        aliases = {'dep': 'depends', 'scr': 'scry', 'exit': 'quit', 'q': 'quit'}
        argv = full_command.split(' ')
        argv[0] = aliases.get(argv[0], argv[0])
        cmd = argv[0]
        if self.whitelist is not None and cmd not in self.whitelist:
            print("Command now allowed:", cmd)
            assert(0)

        if cmd not in self.all_cmds:
            print("Unknown command:", '"'+cmd+'"')
            print(f"{argv=}")
            assert(0)
        args = self.parser.parse_args(argv)
        getattr(self, 'cmd_'+cmd)(args)
