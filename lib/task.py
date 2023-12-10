import dateutil.parser
from datetime import datetime
import parsedatetime as pdt
import sqlite3

class Task:
    def __init__(self, ctx, taskdict):
        self.ctx = ctx
        self.cur = ctx.cur
        keys = list(self.cur.execute("pragma table_info(tasks)").fetchall())
        keys = [i['name'] for i in keys]
        for i in keys:
            if i not in taskdict.keys():
                taskdict[i] = None
        for k, v in taskdict.items():
            exec('self.' + k + ' = v')
        
        if self.tags is None:
            self.tags = []
        else:
            self.tags = [i.strip() for i in self.tags.split(' ')]

        if self.status is not None:
            self.status = dateutil.parser.parse(self.status)
        if self.due is not None:
            self.due = dateutil.parser.parse(self.due)
        if self.start is not None:
            self.start = dateutil.parser.parse(self.start)

        self.gauge = self.gauge if self.gauge is not None else 0

        if self.depends is None:
            self.depends = []
        elif type(self.depends) == str:
            self.depends = [int(i) for i in self.depends.split(' ') if i != '']


    def __str__(self):
        parent = self.get_parent()
        parent_str = '' if parent is None else parent.desc+'/'
        time_desc = []
        if self.due:
            time_desc.append('due '+str(self.due))
        if self.start:
            time_desc.append('starts '+str(self.start))
        if self.repeat:
            time_desc.append('repeats '+str(self.repeat))

        dep_desc = None
        if self.depends != []:
            dep_desc = "Depends on "+' '.join([str(i) for i in self.depends])

        ret = '('+str(self.uuid)+') "' + parent_str + self.desc + '"'
        if time_desc != []:
            ret += '\n' + ', '.join(time_desc)
        if dep_desc is not None:
            ret += '\n' + dep_desc
        return ret


    def get_parent(self):
        if self.parent is None:
            return None
        else:
            return Task(self.ctx, dict(self.cur.execute('SELECT * FROM tasks WHERE uuid = {}'.format(self.parent)).fetchone()))


    def has_tag(self, tag):
        return tag in self.tags


    def get_children(self, filters=[], allow_none=True):
        """Returns all children of current tasks.

        Parameters
        ----------
        filters : list
            Array of functions that takes a task and return whether or not the current task should be filtered out.

        Returns
        -------
        list
            List of children tasks not blocked by filters.
        """
        if self.uuid is None:
            assert allow_none
            l = list(self.cur.execute('select * from tasks where parent IS NULL').fetchall())
        else:
            l = list(self.cur.execute('select * from tasks where parent = {}'.format(self.uuid)).fetchall())
            assert(self.uuid != self.parent)
        l = [Task(self.ctx, dict(i)) for i in l]
        children = l[:]
        if filters != []:
            children = [i for i in children if not i.is_filtered(filters)]
        return children


    def get_pending_children(self):
        return list(self.cur.execute('select * from tasks where parent = {} and status IS NULL'.format(self.uuid)).fetchall())


    def get_pending_dependency(self):
        """Returns all unfinished tasks the current task is dependent on"""
        if self.depends is None:
            return []
        deps = [str(i) for i in self.depends]
        # array of dependecies that have not been completed
        unsatis = list(self.cur.execute('SELECT * FROM tasks WHERE status IS NULL AND uuid IN ({})'.format(', '.join(deps))).fetchall())
        return [Task(self.ctx, dict(i)) for i in unsatis]


    def has_pending_dependency(self):
        return len(self.get_pending_dependency()) > 0


    def get_rel_path(self):
        """Returns the path (eg. "../task1/subtask2") relative to the context's working task."""
        path = self.desc
        ct = self

        # Move up in the task tree until you get to a task that has both the
        # working task and current task as descendents
        common_parent = self.ctx.working_task
        prefix = ''
        while common_parent is not None and not self.is_descendant(common_parent.uuid):
            common_parent = common_parent.get_parent()
            prefix += '../'
            print(common_parent)
        common_parent = common_parent.uuid if common_parent else None
        assert(self.is_descendant(common_parent))

        # Get path from the common ancestor
        while ct.parent != common_parent:
            ct = ct.get_parent()
            path = ct.desc + '/' + path
        return prefix + path;


    def is_filtered(self, filters):
        return True in [i(self) for i in filters]


    def is_due(self, curtime = datetime.now()):
        return (self.due is None or self.due <= curtime)


    def has_started(self, curtime = datetime.now()):
        if self.start is None or self.start <= curtime:
            if self.parent is None:
                return True
            else:
                return self.get_parent().has_started(curtime)
        else:
            return False


    def has_finished_after(self, curtime = datetime.now(), partial=False):
        """Returns whether the current task has been (partially if partial=True) completed after curtime."""
        if not partial:
            return (self.status is not None and self.status >= curtime)
        # If partial, we check (recursively) whether there is any children
        # that has also been partially finished after curtime.
        children = self.get_children()
        if len(children) == 0:
            return (self.status is not None and self.status >= curtime)
        return True in [i.has_finished_after(curtime, True) for i in children]


    def get_earliest_due(self, due_limit=None, start_limit=datetime.now(), filters=[]):
        """Return the earliest due date of all descendants that have all already started and are not blocked by filters.
        Any due date after due_limit or task not started before start_limit is ignored.
        Returns None if there are no due tasks satisfying our criteria."""
        descendants = self.get_descendants(filters + [lambda x: x.has_started(start_limit)])
        descendants.append(self) # We care about our own due date too
        dues = []
        for i in descendants:
            if due_limit is None or i.is_due(due_limit):
                dues.append(i.due)

        dues = [i for i in dues if i is not None]
        return min(dues) if len(dues) > 0 else None


    def is_descendant(self, root: int):
        if self.uuid == root or self.parent == root:
            return True
        elif self.parent is None:
            return False
        else:
            return self.get_parent().is_descendant(root)


    def get_descendants(self, filters=[]):
        # TODO: Do this with a recursive query or at least as many queries as
        # the depth of the task tree.
        children = self.get_children(filters, False)
        descendants = children[:]
        assert False not in [i.parent == self.uuid for i in children]
        for i in children:
            desc = i.get_descendants(filters)[:]
            for j in desc:
                if j.uuid in [k.uuid for k in descendants]:
                    print("Conflict found:")
                    print(vars(j))
                    print(vars([k for k in descendants if k.uuid == j.uuid][0]))
                    print([k for k in descendants if k.uuid == j.uuid][0] == j)
                    assert(0)
            descendants += desc
        return descendants


# ------------------------------------------------------------------------------
# Modifiers
# ------------------------------------------------------------------------------
    def write_str(self, attr, val):
        if val is not None:
            val = str(val)
            val = val.replace("'", "''")
            val = val.replace('"', '""')
        if val is None:
            self.cur.execute("UPDATE tasks SET {} = NULL WHERE uuid = {}".format(attr, self.uuid)) 
        else:
            self.cur.execute("UPDATE tasks SET {} = '{}' WHERE uuid = {}".format(attr, val, self.uuid)) 


    def write_int(self, attr, val):
        self.cur.execute("UPDATE tasks SET {} = {} WHERE uuid = {}".format(attr, 'NULL' if val is None else val, self.uuid)) 


    def add_dependency(self, dep):
        self.depends = self.depends + [dep]
        self.write_str('depends', self.get_depends_str()) 


    def update_uuid(self, new_uuid):
        old_uuid = self.uuid
        self.write_int('uuid', new_uuid)
        self.cur.execute("UPDATE tasks SET parent = '{}' WHERE parent = {}".format(new_uuid, old_uuid)) 
        self.cur.execute("UPDATE tasks SET depends = replace(depends, ' {} ', ' {} ')".format(old_uuid, new_uuid)) 


    def update_gauge(self, new_gauge):
        old_gauge = self.gauge
        delta_gauge = new_gauge - old_gauge
        self.write_int('gauge', new_gauge)
        for i in self.get_children():
            i.update_gauge(i.gauge + delta_gauge)


    def add_tags(self, new_tags):
        self.tags += new_tags
        self.write_str('tags', self.get_tags_str())


    def remove_tags(self, to_remove):
        self.tags = [i for i in self.tags if i not in to_remove]
        self.write_str('tags', self.get_tags_str())


    def get_tags_str(self):
        return ' '+ ' '.join(self.tags).strip() + ' '


    def get_depends_str(self):
        return ' '+ ' '.join([str(i) for i in self.depends]) + ' '
