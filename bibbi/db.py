import pyodbc


class Db:

    def __init__(self, server, database):
        self.conn = pyodbc.connect(
            'Driver={SQL Server};'
            'Server=%s;'
            'Database=%s;'
            'Trusted_Connection=yes;'
            % (server, database)
        )

    def cursor(self):
        return self.conn.cursor()


def main():
    db = Db('Sindre', 'Promus')
    cursor = db.cursor()
    cursor.execute('SELECT * FROM dbo.AuthorityTopic')

    columns = [column[0] for column in cursor.description]
    for col in columns:
        print(col)

    for row in cursor:
        print(row)
        break
