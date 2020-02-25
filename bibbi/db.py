import pyodbc
import os


class Db:

    def __init__(self, **db_settings):
        if os.name == 'posix':
            conn_string = ';'.join([
                'DRIVER={FreeTDS}',
                'Server=%(server)s',
                'Database=%(database)s',
                'UID=BIBSENT\\dmheg',
                'PWD=%(password)s',
                'TDS_Version=8.0',
                'Port=1433',
            ]) % db_settings
        else:
            conn_string = ';'.join([
                'Driver={SQL Server}',
                'Server=%(server)s',
                'Database=%(database)s',
                'Trusted_Connection=yes',
            ]) % db_settings
        self.conn = pyodbc.connect(conn_string            )

    def cursor(self):
        return self.conn.cursor()


def main(db_settings):
    db = Db(db_settings)
    cursor = db.cursor()
    cursor.execute('SELECT * FROM dbo.AuthorityTopic')

    columns = [column[0] for column in cursor.description]
    for col in columns:
        print(col)

    for row in cursor:
        print(row)
        break
