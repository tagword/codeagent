"""
数据库工具 — 支持 SQLite / PostgreSQL / MySQL

子命令:
  connect  连接数据库  db(command="connect", dsn="sqlite:///test.db")
  tables   列出所有表  db(command="tables")
  schema   查看表结构  db(command="schema", table="users")
  query    执行查询    db(command="query", sql="SELECT * FROM users LIMIT 10")
  execute  执行写操作  db(command="execute", sql="INSERT INTO ...")
  models   生成 ORM 模型占位 db(command="models")
"""

import os
import sqlite3
from typing import Any, Dict, List, Tuple

from seed_tools.models import Tool

# 单例：当前数据库连接
_current_conn: Any = None
_current_dsn: str = ""
_current_db_type: str = ""


def _format_table(data: List[Tuple], headers: List[str], max_rows: int = 30) -> str:
    """Format query results as a readable table."""
    if not data:
        return "(空结果集)"

    rows = data[:max_rows]
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            w = len(str(cell)) if cell is not None else 4
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], w)

    col_widths = [min(w, 60) for w in col_widths]

    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    def fmt_row(vals) -> str:
        cells = []
        for i, v in enumerate(vals):
            s = str(v) if v is not None else "NULL"
            if len(s) > col_widths[i]:
                s = s[:col_widths[i] - 3] + "..."
            cells.append(f" {s:<{col_widths[i]}} ")
        return "|" + "|".join(cells) + "|"

    lines = [sep, fmt_row(headers), sep]
    for row in rows:
        lines.append(fmt_row(row))
    lines.append(sep)

    if len(data) > max_rows:
        lines.append(f"... 还有 {len(data) - max_rows} 行未显示")

    return "\n".join(lines)


def _parse_dsn(dsn: str) -> Tuple[str, dict]:
    """Parse DSN and return (db_type, params)."""
    if dsn.startswith("sqlite:///"):
        path = dsn[len("sqlite:///"):]
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        return "sqlite", {"database": path}
    elif dsn.startswith("sqlite://"):
        path = dsn[len("sqlite://"):]
        return "sqlite", {"database": path}
    elif dsn.startswith("postgresql://") or dsn.startswith("postgres://"):
        return "postgresql", {"dsn": dsn}
    elif dsn.startswith("mysql://") or dsn.startswith("mysql+pymysql://"):
        return "mysql", {"dsn": dsn}
    else:
        path = dsn
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        return "sqlite", {"database": path}


def _connect_sqlite(params: dict) -> Tuple[Any, str]:
    """Connect to SQLite database."""
    db_path = params["database"]
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn, f"sqlite:///{db_path}"


def _try_connect(dsn: str) -> Tuple[bool, str]:
    """Try to connect to the database."""
    global _current_conn, _current_dsn, _current_db_type

    db_type, params = _parse_dsn(dsn)

    try:
        if db_type == "sqlite":
            _current_conn, resolved_dsn = _connect_sqlite(params)
        elif db_type in ("postgresql", "mysql"):
            try:
                import importlib
                driver = "psycopg2" if db_type == "postgresql" else "pymysql"
                mod = importlib.import_module(driver)
                if db_type == "postgresql":
                    _current_conn = mod.connect(params["dsn"])
                else:
                    _current_conn = mod.connect(params["dsn"])
                resolved_dsn = params["dsn"]
            except ImportError:
                return False, f"❌ 需要安装 {driver}: pip install {driver}"
            except Exception as e:
                return False, f"❌ 连接失败: {e}"

        _current_dsn = resolved_dsn
        _current_db_type = db_type
        return True, f"✅ 已连接: {resolved_dsn}"

    except Exception as e:
        return False, f"❌ 连接失败: {e}"


def _get_tables() -> List[str]:
    """获取当前数据库的所有表名。"""
    global _current_conn
    if not _current_conn:
        return []

    try:
        cursor = _current_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]
    except Exception:
        return []


def _get_table_schema(table: str) -> List[Dict]:
    """获取表结构。"""
    global _current_conn
    if not _current_conn:
        return []

    try:
        cursor = _current_conn.execute(f"PRAGMA table_info('{table}')")
        columns = cursor.fetchall()
        return [
            {
                "name": col[1],
                "type": col[2],
                "nullable": not col[3],
                "default": col[4],
                "pk": bool(col[5]),
            }
            for col in columns
        ]
    except Exception:
        return []


def db_handler(command: str = "", dsn: str = "", table: str = "",
               sql: str = "", limit: int = 30) -> str:
    """
    数据库工具 — 支持 SQLite / PostgreSQL / MySQL。

    子命令:
      connect  连接数据库
      tables   列出所有表
      schema   查看表结构
      query    执行查询
      execute  执行写操作
      models   生成 ORM 模型占位
    """
    global _current_conn

    cmd = command.strip().lower()

    if not cmd or cmd == "help":
        return (
            "📗 **db 工具使用帮助**\n\n"
            "子命令:\n"
            '  connect dsn="sqlite:///test.db"  连接数据库\n'
            "  tables                           列出所有表\n"
            '  schema table="users"              查看表结构\n'
            '  query sql="SELECT * FROM users"   执行查询\n'
            '  execute sql="INSERT INTO ..."     执行写操作\n'
            '  models                            生成 ORM 模型文本\n\n'
            "DSN 格式:\n"
            "  sqlite:///path/to/db.db\n"
            "  postgresql://user:pass@host:port/dbname\n"
            "  mysql://user:pass@host:port/dbname"
        )

    try:
        if cmd == "connect":
            if not dsn:
                return "❌ connect 需要 dsn 参数"
            ok, msg = _try_connect(dsn)
            return msg

        if cmd == "tables":
            if not _current_conn:
                return "❌ 请先 connect 到数据库"
            tables = _get_tables()
            if not tables:
                return "📭 该数据库中没有表"
            return "📋 **表列表:**\n\n" + "\n".join(f"  📄 `{t}`" for t in tables)

        if cmd == "schema":
            if not _current_conn:
                return "❌ 请先 connect 到数据库"
            if not table:
                return "❌ schema 需要 table 参数"
            cols = _get_table_schema(table)
            if not cols:
                return f"❌ 未找到表: {table}"
            lines = [f"📋 **表结构: {table}**\n"]
            lines.append("  ┌──────┬─────────────┬──────┬────────┐")
            lines.append("  │ 字段  │ 类型        │ 可空 │ 主键   │")
            lines.append("  ├──────┼─────────────┼──────┼────────┤")
            for col in cols:
                nullable = "YES" if col["nullable"] else "NO"
                pk = "PK" if col["pk"] else ""
                lines.append(f"  │ {col['name']:<4} │ {col['type']:<11} │ {nullable:<4} │ {pk:<6} │")
            lines.append("  └──────┴─────────────┴──────┴────────┘")
            return "\n".join(lines)

        if cmd == "query":
            if not _current_conn:
                return "❌ 请先 connect 到数据库"
            if not sql:
                return "❌ query 需要 sql 参数"
            cursor = _current_conn.execute(sql)
            rows = cursor.fetchall()
            headers = [desc[0] for desc in cursor.description] if cursor.description else []
            if not rows:
                return "📭 查询结果为空"
            return _format_table(rows, headers, max_rows=limit)

        if cmd == "execute":
            if not _current_conn:
                return "❌ 请先 connect 到数据库"
            if not sql:
                return "❌ execute 需要 sql 参数"
            cursor = _current_conn.execute(sql)
            _current_conn.commit()
            return f"✅ 执行成功, 影响 {cursor.rowcount} 行"

        if cmd == "models":
            if not _current_conn:
                return "❌ 请先 connect 到数据库"
            tables = _get_tables()
            if not tables:
                return "📭 该数据库中没有表，无法生成模型"
            lines = ["# 数据库 ORM 模型 (SQLAlchemy 参考)\n", "from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime\n",
                     "from sqlalchemy.orm import declarative_base\n",
                     "Base = declarative_base()\n"]
            for t in tables:
                cols = _get_table_schema(t)
                class_name = "".join(word.capitalize() for word in t.split("_"))
                lines.append(f"\nclass {class_name}(Base):")
                lines.append(f"    __tablename__ = '{t}'")
                for col in cols:
                    col_type = col["type"].upper()
                    sa_type = "String"
                    if "INT" in col_type:
                        sa_type = "Integer"
                    elif "CHAR" in col_type or "TEXT" in col_type:
                        sa_type = "String"
                    elif "FLOAT" in col_type or "DOUBLE" in col_type:
                        sa_type = "Float"
                    elif "BOOL" in col_type:
                        sa_type = "Boolean"
                    nullable = "" if col["nullable"] else ", nullable=False"
                    pk = ", primary_key=True" if col["pk"] else ""
                    lines.append(f"    {col['name']} = Column({sa_type}{pk}{nullable})")
            return "\n".join(lines)

        return f"❌ 未知子命令: {command}"

    except Exception as e:
        return f"❌ 操作失败: {e}"


db_tool_def = Tool(
    name="db",
    description="数据库工具，支持 SQLite/PostgreSQL/MySQL 的连接、查询、表结构查看和 ORM 模型生成。",
    parameters={
        "command": {"type": "string", "required": True, "description": "子命令: connect, tables, schema, query, execute, models"},
        "dsn": {"type": "string", "required": False, "description": "数据库 DSN（connect 使用）"},
        "table": {"type": "string", "required": False, "description": "表名（schema, models 使用）"},
        "sql": {"type": "string", "required": False, "description": "SQL 语句（query, execute 使用）"},
        "limit": {"type": "integer", "required": False, "description": "最大返回行数（query 使用，默认 30）"},
    },
    returns="string",
    category="dev",
)
