from django.core import signals
from django.db.utils import (
    DEFAULT_DB_ALIAS, DJANGO_VERSION_PICKLE_KEY, ConnectionHandler,
    ConnectionRouter, DatabaseError, DataError, Error, IntegrityError,
    InterfaceError, InternalError, NotSupportedError, OperationalError,
    ProgrammingError,
)

__all__ = [
    'backend', 'connection', 'connections', 'router', 'DatabaseError',
    'IntegrityError', 'InternalError', 'ProgrammingError', 'DataError',
    'NotSupportedError', 'Error', 'InterfaceError', 'OperationalError',
    'DEFAULT_DB_ALIAS', 'DJANGO_VERSION_PICKLE_KEY'
]

# 实例化连接，获取数据库配置
connections = ConnectionHandler()

# 数据库路由，获取路由配置
router = ConnectionRouter()


# `connection`, `DatabaseError` and `IntegrityError` are convenient aliases
# for backend bits.

# DatabaseWrapper.__init__() takes a dictionary, not a settings module, so we
# manually create the dictionary from the settings, passing only the settings
# that the database backends care about.
# We load all these up for backwards compatibility, you should use
# connections['default'] instead.
class DefaultConnectionProxy(object):
    """
    Proxy for accessing the default DatabaseWrapper object's attributes. If you
    need to access the DatabaseWrapper object itself, use
    connections[DEFAULT_DB_ALIAS] instead.
    """

    def __getattr__(self, item):
        return getattr(connections[DEFAULT_DB_ALIAS], item)

    def __setattr__(self, name, value):
        return setattr(connections[DEFAULT_DB_ALIAS], name, value)

    def __delattr__(self, name):
        return delattr(connections[DEFAULT_DB_ALIAS], name)

    def __eq__(self, other):
        return connections[DEFAULT_DB_ALIAS] == other

    def __ne__(self, other):
        return connections[DEFAULT_DB_ALIAS] != other


connection = DefaultConnectionProxy()  # 默认的连接代理，用于获取、设置、删除、比较connections的连接信息


# Register an event to reset saved queries when a Django request is started.
# 将全部连接的全部查询log清空
def reset_queries(**kwargs):
    for conn in connections.all():
        conn.queries_log.clear()


# 每个请求开启数据库连接并清空log
signals.request_started.connect(reset_queries)


# Register an event to reset transaction state and close connections past
# their lifetime.
# 关闭无效或者过期的连接
def close_old_connections(**kwargs):
    for conn in connections.all():
        conn.close_if_unusable_or_obsolete()


# 在请求开始和结束都关闭旧连接
signals.request_started.connect(close_old_connections)
signals.request_finished.connect(close_old_connections)
