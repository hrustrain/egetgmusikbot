# database.py
import aiosqlite

DB_PATH = "tasks.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                answer TEXT NOT NULL
            )
        """)
        await db.commit()

async def get_answer(task_id: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT answer FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        return row[0] if row else None