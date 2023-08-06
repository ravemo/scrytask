import sqlite3
import task

class Context:
    def __init__(self, cur):
        self.cur = cur
        self.working_task = None

    def get_working_uuid(self):
        return self.working_task.uuid if self.working_task else None

    def get_descendants(self):
        if self.working_task is None:
            return [task.Task(self, dict(i)) for i in self.cur.execute("SELECT * FROM tasks").fetchall()]
        else:
            return self.working_task.get_descendants()
