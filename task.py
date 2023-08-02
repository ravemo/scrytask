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
        
        if self.tags == None:
            self.tags = []
        else:
            self.tags = [i.strip() for i in self.tags.split(' ')]

        if self.status != None:
            self.status = dateutil.parser.parse(self.status)
        if self.due != None:
            self.due = dateutil.parser.parse(self.due)
        if self.start != None:
            self.start = dateutil.parser.parse(self.start)

        self.gauge = self.gauge if self.gauge != None else 0

        if self.depends == None:
            self.depends = []
        elif type(self.depends) == str:
            self.depends = [int(i) for i in self.depends.split(' ') if i != '']


    def __str__(self):
        parent = self.get_parent()
        parent_str = '' if parent == None else parent.desc+'/'
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
        if dep_desc != None:
            ret += '\n' + dep_desc
        return ret


    def get_parent(self):
        if self.parent == None:
            return None
        else:
            return Task(self.ctx, dict(self.cur.execute('SELECT * FROM tasks WHERE uuid = {}'.format(self.parent)).fetchone()))


    def has_tag(self, tag):
        return tag in self.tags


    def get_children(self, filters=[]):
        if self.uuid == None:
            l = list(self.cur.execute('select * from tasks where parent IS NULL').fetchall())
        else:
            l = list(self.cur.execute('select * from tasks where parent = {}'.format(self.uuid)).fetchall())
        l = [Task(self.ctx, dict(i)) for i in l]
        children = [i for i in l if not i.is_filtered(filters)]
        if filters != []:
            children = [i for i in children if not i.is_filtered(filters)]
        return children


    def get_pending_children(self):
        return list(self.cur.execute('select * from tasks where parent = {} and status IS NULL'.format(self.uuid)).fetchall())


    def get_pending_dependency(self):
        if self.depends == None:
            return []
        deps = [str(i) for i in self.depends]
        # array of dependecies that have not been completed
        unsatis = list(self.cur.execute('SELECT * FROM tasks WHERE status IS NULL AND uuid IN ({})'.format(', '.join(deps))).fetchall())
        return [Task(self.ctx, dict(i)) for i in unsatis]


    def has_pending_dependency(self):
        return len(self.get_pending_dependency()) > 0


    def get_rel_path(self):
        path = self.desc
        ct = self

        # Move up in the task tree until you get to a task that has both the
        # working task and current task as descendents
        common_parent = self.ctx.working_task
        prefix = ''
        while common_parent != None and not self.is_descendant(common_parent.uuid):
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


    def is_dependent(self):
        deps = self.get_pending_dependency()
        return True in [i.is_dependent() for i in deps]


    def is_filtered(self, filters):
        return True in [i(self) for i in filters]


    def is_due(self, curtime = datetime.now()):
        return (self.due == None or self.due <= curtime)


    def has_started(self, curtime = datetime.now()):
        if self.start == None or self.start <= curtime:
            if self.parent == None:
                return True
            else:
                return self.get_parent().has_started(curtime)
        else:
            return False


    def has_finished_after(self, curtime = datetime.now()):
        return (self.status != None and self.status >= curtime)


    def get_earliest_due(self, limit=datetime.now(), filters=[]):
        children = self.get_children(filters)
        if len(children) == 0:
            if not self.has_started():
                return None
            if self.is_due(limit):
                return self.due

        dues = [i.get_earliest_due(limit, filters) for i in children]
        dues = [i for i in dues if i != None]
        if self.due != None:
            dues = [self.due] + dues

        return min(dues) if len(dues) > 0 else None


    def is_descendant(self, root: int):
        if self.uuid == root or self.parent == root:
            return True
        elif self.parent == None:
            return False
        else:
            return self.get_parent().is_descendant(root)


    def get_descendants(self, filters=[]):
        children = self.get_children(filters)
        descendants = children
        for i in children:
            descendants += i.get_descendants(filters)
        return descendants


# ------------------------------------------------------------------------------
# Modifiers
# ------------------------------------------------------------------------------
    def write_str(self, attr, val):
        if val != None:
            val = str(val)
            val = val.replace("'", "''")
            val = val.replace('"', '""')
        if val == None:
            self.cur.execute("UPDATE tasks SET {} = NULL WHERE uuid = {}".format(attr, self.uuid)) 
        else:
            self.cur.execute("UPDATE tasks SET {} = '{}' WHERE uuid = {}".format(attr, val, self.uuid)) 


    def write_int(self, attr, val):
        self.cur.execute("UPDATE tasks SET {} = {} WHERE uuid = {}".format(attr, 'NULL' if val == None else val, self.uuid)) 


    def add_dependency(self, dep):
        self.depends = self.depends + [dep]
        new_depends_str = ' ' + ' '.join([str(i) for i in self.depends]) + ' '
        self.write_str('depends', new_depends_str) 


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
        tags_str = ' '+ ' '.join(self.tags).strip() + ' '
        print("New tags:", "'"+tags_str+"'")
        self.write_str('tags', tags_str)


    def remove_tags(self, to_remove):
        self.tags = [i for i in self.tags if i not in to_remove]
        tags_str = ' '+ ' '.join(self.tags).strip() + ' '
        print("New tags:", "'"+tags_str+"'")
        self.write_str('tags', tags_str)


    def get_tags_str(self):
        return ' '+ ' '.join(self.tags) + ' '


    def get_depends_str(self):
        return ' '+ ' '.join([str(i) for i in self.depends]) + ' '
