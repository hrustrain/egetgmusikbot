# bot.py
import asyncio
import os
import random
import tempfile

from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile
from aiogram.filters import Command

from config import BOT_TOKEN, IMAGES_DIR, DATABASE_PATH
from database import init_db, get_answer

# ---------- FSM для тренировки ----------
class Training(StatesGroup):
    waiting_for_answer = State()   # ожидаем ответ на задание

class Music(StatesGroup):
    waiting_for_link = State()     # ожидаем ссылку SoundCloud

# ---------- Инициализация ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

VALID_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# ---------- Вспомогательные функции ----------
def get_random_task() -> tuple[str, str] | None:
    """Возвращает (путь к файлу картинки, её id) или None, если заданий нет."""
    try:
        files = [f for f in os.listdir(IMAGES_DIR)
                 if os.path.splitext(f)[1].lower() in VALID_IMAGE_EXTS]
    except FileNotFoundError:
        return None
    if not files:
        return None
    chosen = random.choice(files)
    task_id = os.path.splitext(chosen)[0]
    return os.path.join(IMAGES_DIR, chosen), task_id

async def send_random_task(message: types.Message, state: FSMContext):
    """Отправляет случайное задание и переводит бота в ожидание ответа."""
    task_info = get_random_task()
    if task_info is None:
        await message.answer("😕 Нет доступных заданий. Добавьте картинки в папку images/")
        return

    image_path, task_id = task_info
    answer = await get_answer(task_id)
    if answer is None:
        await message.answer(f"⚠️ Для задания {task_id} не найден ответ в базе. Пропускаю.")
        return

    # Сохраняем правильный ответ в состоянии
    await state.update_data(correct_answer=answer.strip().lower())
    await state.set_state(Training.waiting_for_answer)

    # Отправляем картинку
    photo = FSInputFile(image_path)
    await message.answer_photo(photo, caption="Введите ответ (число или выражение):")

# ---------- Команды ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я помогу подготовиться к тестовой части ЕГЭ по профильной математике.\n"
        "/train – начать решать задания (случайные)\n"
        "/music – получить трек со SoundCloud для фона\n"
        "/stop – выйти из текущего режима"
    )

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Вы не в активном режиме.")
        return
    await state.clear()
    await message.answer("Режим остановлен. Возвращайтесь!")

# ---------- Режим тренировки ----------
@dp.message(Command("train"))
async def cmd_train(message: types.Message, state: FSMContext):
    await state.clear()  # на всякий случай сбрасываем другие состояния
    await send_random_task(message, state)

# Обработка ответа в режиме тренировки
@dp.message(Training.waiting_for_answer)
async def process_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    correct = data.get("correct_answer")
    user_answer = message.text.strip().lower()

    if user_answer == correct:
        await message.answer("🎉 Верно! Молодец!")
    else:
        await message.answer(f"❌ Неверно. Правильный ответ: {correct}. Не расстраивайся, в следующий раз получится!")

    # Сразу предлагаем следующее задание
    await send_random_task(message, state)

# ---------- Режим музыки (SoundCloud) ----------
@dp.message(Command("music"))
async def cmd_music(message: types.Message, state: FSMContext):
    await state.set_state(Music.waiting_for_link)
    await message.answer("🎵 Я готов принять ссылку на трек со SoundCloud. Отправь её сюда.")

@dp.message(Music.waiting_for_link, F.text.contains("soundcloud.com"))
async def process_soundcloud_link(message: types.Message, state: FSMContext):
    url = message.text.strip()
    await message.answer("⏳ Скачиваю трек, подожди немного...")

    loop = asyncio.get_running_loop()
    try:
        # Загрузка через yt-dlp в отдельном потоке
        audio_path = await loop.run_in_executor(
            None, download_soundcloud, url
        )
        # Отправляем аудио
        audio_file = FSInputFile(audio_path)
        await message.answer_audio(audio_file, title="Твой трек 🎶")
        # Удаляем временный файл
        os.remove(audio_path)
    except Exception as e:
        await message.answer(f"😞 Не удалось скачать трек: {e}")
    finally:
        await state.clear()

def download_soundcloud(url: str) -> str:
    """Синхронная функция для загрузки аудио в временный файл. Возвращает путь к mp3."""
    import yt_dlp

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': tempfile.mktemp(suffix='.mp3'),
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # yt-dlp может переименовать файл, поэтому ищем фактический mp3 в tmp
        # Проще: задать outtmpl с фиксированным именем, но у нас уже задано
        # Мы используем 'outtmpl', поэтому после загрузки файл будет по указанному пути.
    # yt-dlp добавляет расширение .mp3 после постобработки, путь в outtmpl уже с .mp3
    return ydl_opts['outtmpl']

# ---------- Старт ----------
async def main():
    await init_db()
    print("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())