"""Compatibility imports for code that still references the old SQLAgent name."""

try:
    from .new_sql_agent import NewSQLAgent, execute_sql_safe
except ImportError:
    from new_sql_agent import NewSQLAgent, execute_sql_safe


SQLAgent = NewSQLAgent

__all__ = ["SQLAgent", "NewSQLAgent", "execute_sql_safe"]
