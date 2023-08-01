import sqlite3

class Context:
    def __init__(self, cur):
        self.cur = cur
        self.working_task = None

    def get_working_uuid(self):
        return self.working_task.uuid if self.working_task else None
