"""Compose existing Core writes without committing a caller's transaction."""
from uuid import uuid4


class WriteScope:
    def __init__(self,connection):
        self.db=connection;self.name='write_'+uuid4().hex if connection.in_transaction else None
        self.done=False
        connection.execute('SAVEPOINT '+self.name if self.name else 'BEGIN IMMEDIATE')

    def commit(self):
        self.db.execute('RELEASE SAVEPOINT '+self.name if self.name else 'COMMIT');self.done=True

    def rollback(self):
        if self.done:return
        if self.name:
            self.db.execute('ROLLBACK TO SAVEPOINT '+self.name)
            self.db.execute('RELEASE SAVEPOINT '+self.name)
        else:self.db.execute('ROLLBACK')
        self.done=True
