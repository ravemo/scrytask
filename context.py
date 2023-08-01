import sqlite3

class Context:
    def __init__(self, cur):
        self.cur = cur
        self.working_task = None
