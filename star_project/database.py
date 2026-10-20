import os
import json
import sqlite3
from datetime import datetime
from contextlib import closing

# ============================================================
# 数据库路径：chat_history.db 位于项目根目录（star_project 的上一级）
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "chat_history.db")


# 获取数据库连接（Row 工厂让查询结果可按列名访问）
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# 初始化数据库：建 messages（消息）和 sessions（会话元数据）两张表
# ============================================================
def init_db():
    with closing(get_db_connection()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                thread_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                uid TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()


# ============================================================
# 保存一条消息（非字符串内容会先转成 JSON 字符串）
# ============================================================
def save_message(thread_id: str, role: str, content: str):
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    with closing(get_db_connection()) as conn:
        conn.execute(
            "INSERT INTO messages (thread_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (thread_id, role, content, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()


# ============================================================
# 按 thread_id 读取全部历史消息（按 id 升序保证对话顺序）
# ============================================================
def load_history(thread_id: str):
    with closing(get_db_connection()) as conn:
        rows = conn.execute(
            "SELECT id, thread_id, role, content, created_at FROM messages WHERE thread_id = ? ORDER BY id ASC",
            (thread_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ============================================================
# 查询所有出现过的 thread_id（sessions 表为空时兜底用）
# ============================================================
def load_all_thread_ids():
    with closing(get_db_connection()) as conn:
        rows = conn.execute(
            "SELECT DISTINCT thread_id FROM messages ORDER BY thread_id"
        ).fetchall()
    return [r["thread_id"] for r in rows]


# ============================================================
# 新增或更新会话元数据（thread_id 与自定义标题、uid 绑定）
# ============================================================
def upsert_session(thread_id: str, title: str, uid: str = None):
    with closing(get_db_connection()) as conn:
        conn.execute("""
            INSERT INTO sessions (thread_id, title, uid, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                title = excluded.title,
                uid = COALESCE(excluded.uid, sessions.uid),
                updated_at = excluded.updated_at
        """, (thread_id, title, uid, datetime.now().isoformat(timespec="seconds")))
        conn.commit()


# ============================================================
# 读取单个会话的元数据（不存在返回 None）
# ============================================================
def get_session(thread_id: str):
    with closing(get_db_connection()) as conn:
        row = conn.execute(
            "SELECT thread_id, title, uid, updated_at FROM sessions WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
    return dict(row) if row else None


# ============================================================
# 读取所有会话元数据（按更新时间倒序，供前端侧边栏使用）
# ============================================================
def load_all_sessions():
    with closing(get_db_connection()) as conn:
        rows = conn.execute(
            "SELECT thread_id, title, uid, updated_at FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ============================================================
# 删除一个会话：messages 和 sessions 中的记录一起删掉
# ============================================================
def delete_session(thread_id: str):
    with closing(get_db_connection()) as conn:
        conn.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
        conn.execute("DELETE FROM sessions WHERE thread_id = ?", (thread_id,))
        conn.commit()