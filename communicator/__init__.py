# PyMySQL is used instead of mysqlclient because shared cPanel hosting
# frequently lacks a C compiler/dev headers needed to build mysqlclient's
# extension, while PyMySQL is pure-Python and installs anywhere pip does.
#
# This shim must live here (imported the moment the `communicator` package
# is imported) rather than in passenger_wsgi.py: manage.py migrate/
# collectstatic/shell all import this package directly and never touch
# passenger_wsgi.py, so a shim placed only there leaves every manual
# management command on the server failing with "No module named MySQLdb".
try:
    import pymysql

    pymysql.install_as_MySQLdb()
except ImportError:
    # Not installed when running with USE_MYSQL unset (local SQLite dev).
    pass
