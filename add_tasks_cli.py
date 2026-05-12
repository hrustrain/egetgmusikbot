# add_tasks_cli.py
import os
import asyncio
import aiosqlite
from config import IMAGES_DIR, DATABASE_PATH

VALID_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

async def add_missing_tasks():
    # Получаем все файлы картинок
    try:
        all_files = [f for f in os.listdir(IMAGES_DIR)
                     if os.path.splitext(f)[1].lower() in VALID_IMAGE_EXTS]
    except FileNotFoundError:
        print(f"Папка {IMAGES_DIR} не найдена. Создайте её и положите картинки.")
        return

    if not all_files:
        print("В папке images нет картинок.")
        return

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT id FROM tasks")
        existing_ids = {row[0] for row in await cursor.fetchall()}

    missing = [f for f in all_files if os.path.splitext(f)[0] not in existing_ids]
    if not missing:
        print("Все картинки уже имеют ответы в базе. Добавлять нечего.")
        return

    print(f"Найдено {len(missing)} новых заданий без ответов.\n")
    for img_file in missing:
        task_id = os.path.splitext(img_file)[0]
        answer = input(f"Введите ответ для задания {img_file} (или 'пропустить' для пропуска): ").strip()
        if answer.lower() == 'пропустить':
            continue
        # Сохраняем в БД
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO tasks (id, answer) VALUES (?, ?)",
                (task_id, answer.lower())
            )
            await db.commit()
        print(f"✓ {img_file} -> {answer}")

    print("\nГотово!")

if __name__ == "__main__":
    asyncio.run(add_missing_tasks())