# bot.py
import asyncio
import os
import random
import tempfile
import shutil

from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command

from config import BOT_TOKEN, IMAGES_DIR, DATABASE_PATH, ADMIN_IDS
from database import init_db, get_answer, insert_task


# ---------- Состояния ----------
class Training(StatesGroup):
    waiting_for_answer = State()


class Music(StatesGroup):
    waiting_for_query = State()


class AddTask(StatesGroup):
    waiting_for_image = State()
    waiting_for_answer = State()
    waiting_for_overwrite = State()


# ---------- Инициализация ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

VALID_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


# ---------- Клавиатуры ----------
def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Основная клавиатура с командами."""
    keyboard = [
        [KeyboardButton(text="🎓 /train")],
        [KeyboardButton(text="🎵 /music"), KeyboardButton(text="ℹ️ /help")],
        [KeyboardButton(text="⏹️ /stop")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_train_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура в режиме тренировки."""
    keyboard = [
        [KeyboardButton(text="⏹️ /stop")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_music_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура в режиме музыки."""
    keyboard = [
        [KeyboardButton(text="⏹️ /stop")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# ---------- Утилиты ----------
def get_random_task() -> tuple[str, str] | None:
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
    task_info = get_random_task()
    if task_info is None:
        await message.answer("😕 Нет доступных заданий. Добавьте картинки в папку images/",
                             reply_markup=get_main_keyboard())
        return

    image_path, task_id = task_info
    answer = await get_answer(task_id)
    if answer is None:
        await message.answer(f"⚠️ Для задания {task_id} не найден ответ в базе. Пропускаю.")
        return

    await state.update_data(correct_answer=answer.strip().lower())
    await state.set_state(Training.waiting_for_answer)

    photo = FSInputFile(image_path)
    await message.answer_photo(photo, caption="Введите ответ (число или выражение):", reply_markup=get_train_keyboard())


# ---------- Проверка на админа ----------
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ---------- Команды ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я помогу подготовиться к тестовой части ЕГЭ по профильной математике.\n\n"
        "Нажми на кнопку, чтобы начать:",
        reply_markup=get_main_keyboard()
    )


@dp.message(Command("help"))
@dp.message(F.text == "ℹ️ /help")
async def cmd_help(message: types.Message, state: FSMContext = None):
    # Определяем, из какого режима вызвана помощь
    current_state = await state.get_state() if state else None

    if current_state == Training.waiting_for_answer.state:
        msg = (
            "📚 <b>Режим тренировки</b>\n\n"
            "Бот показывает картинку с заданием. Введи ответ числом или выражением.\n"
            "Примеры: <code>12</code>, <code>3.5</code>, <code>-4</code>\n\n"
            "После ответа сразу получишь новое задание.\n"
            "Для выхода нажми ⏹️ /stop"
        )
    elif current_state == Music.waiting_for_query.state:
        msg = (
            "📚 <b>Режим поиска музыки</b>\n\n"
            "Отправь мне название трека, исполнителя или ссылку на SoundCloud.\n"
            "Я найду первый результат и пришлю аудио.\n\n"
            "Можно отправлять несколько запросов подряд.\n"
            "Для выхода нажми ⏹️ /stop"
        )
    else:
        msg = (
            "📚 <b>Помощь по боту для подготовки к ЕГЭ</b>\n\n"
            "<b>Доступные кнопки:</b>\n"
            "🎓 /train – начать решать задания (случайные)\n"
            "🎵 /music – найти и скачать трек со SoundCloud\n"
            "ℹ️ /help – подсказка по текущему режиму\n"
            "⏹️ /stop – выйти из текущего режима\n\n"
            "<b>Как пользоваться?</b>\n"
            "1. Нажми 🎓 /train, чтобы начать решать. Вводи ответы прямо в чат.\n"
            "2. Нажми 🎵 /music, отправь название трека или ссылку на SoundCloud.\n"
            "3. В режиме музыки можно отправлять несколько запросов подряд.\n"
            "4. Для выхода из любого режима нажми ⏹️ /stop.\n\n"
            "<i>Удачи на ЕГЭ!</i>"
        )

    await message.answer(msg, parse_mode="HTML", reply_markup=get_main_keyboard() if current_state is None else None)


@dp.message(Command("stop"))
@dp.message(F.text == "⏹️ /stop")
async def cmd_stop(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Вы не в активном режиме.", reply_markup=get_main_keyboard())
        return
    await state.clear()
    await message.answer(
        "Режим остановлен. Возвращайтесь!",
        reply_markup=get_main_keyboard()  # Возвращаем основную клавиатуру
    )


# ---------- Режим тренировки ----------
@dp.message(Command("train"))
@dp.message(F.text == "🎓 /train")
async def cmd_train(message: types.Message, state: FSMContext):
    await state.clear()
    await send_random_task(message, state)


@dp.message(Training.waiting_for_answer)
async def process_answer(message: types.Message, state: FSMContext):
    # Если пользователь пытается использовать кнопки во время тренировки
    if message.text in ["⏹️ /stop", "🎓 /train", "🎵 /music", "ℹ️ /help"]:
        return  # Пропускаем, обработается другими хендлерами

    data = await state.get_data()
    correct = data.get("correct_answer")
    user_answer = message.text.strip().lower()

    if user_answer == correct:
        await message.answer("🎉 Верно! Молодец!")
    else:
        await message.answer(f"❌ Неверно. Правильный ответ: {correct}. Не расстраивайся, в следующий раз получится!")

    await send_random_task(message, state)


# ---------- Режим музыки ----------
@dp.message(Command("music"))
@dp.message(F.text == "🎵 /music")
async def cmd_music(message: types.Message, state: FSMContext):
    await state.set_state(Music.waiting_for_query)
    await message.answer(
        "🎵 Отправь мне название трека, исполнителя или ссылку на SoundCloud.\n"
        "Я найду первый результат и пришлю его.\n"
        "Можно присылать несколько запросов подряд. Для выхода нажми ⏹️ /stop.",
        reply_markup=get_music_keyboard()
    )


@dp.message(Music.waiting_for_query, F.text)
async def process_music_query(message: types.Message, state: FSMContext):
    # Если пользователь пытается использовать другие кнопки
    if message.text in ["⏹️ /stop", "🎓 /train", "🎵 /music", "ℹ️ /help"]:
        return  # Пропускаем, обработается другими хендлерами

    query = message.text.strip()
    await message.answer("🔎 Ищу...")

    loop = asyncio.get_running_loop()
    try:
        audio_path, title, performer = await loop.run_in_executor(
            None, download_soundcloud_first_result, query
        )
        audio_file = FSInputFile(audio_path)
        await message.answer_audio(audio_file, title=title, performer=performer)
        os.remove(audio_path)
        await message.answer("✅ Готово! Можешь прислать ещё название или ссылку, или нажми ⏹️ /stop для выхода.")
    except Exception as e:
        await message.answer(f"😞 Не получилось: {e}\nПопробуй ещё раз или нажми ⏹️ /stop.")


# ---------- Режим добавления задания (админ) ----------
@dp.message(Command("add"))
async def cmd_add(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    await state.set_state(AddTask.waiting_for_image)
    await message.answer(
        "📷 Отправьте мне картинку с заданием (фото).",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⏹️ /stop")]],
            resize_keyboard=True
        )
    )


@dp.message(AddTask.waiting_for_image, F.photo)
async def process_task_image(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    file_id = photo.file_id
    temp_path = f"temp_{file_id}.jpg"
    file = await bot.get_file(file_id)
    await bot.download_file(file.file_path, temp_path)

    await state.update_data(temp_image=temp_path)
    await state.set_state(AddTask.waiting_for_answer)
    await message.answer(
        "✅ Картинка получена. Теперь введите **уникальный номер задания** "
        "(например, 105 – это будет имя файла).\n"
        "Затем через пробел – правильный ответ.\n"
        "Пример: <code>105 12</code> или <code>42 3.5</code>",
        parse_mode="HTML"
    )


@dp.message(AddTask.waiting_for_answer)
async def process_task_answer(message: types.Message, state: FSMContext):
    if message.text == "⏹️ /stop":
        return

    data = await state.get_data()
    temp_path = data.get("temp_image")

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("❌ Нужно ввести: НОМЕР_ЗАДАНИЯ ПРОБЕЛ ОТВЕТ\nПример: 105 12")
        return

    task_id, answer = parts[0].strip(), parts[1].strip()
    final_path = os.path.join(IMAGES_DIR, f"{task_id}.jpg")
    if os.path.exists(final_path):
        await message.answer(f"⚠️ Задание с номером {task_id} уже существует. Перезаписать? (да/нет)")
        await state.update_data(pending_task_id=task_id, pending_answer=answer, pending_temp=temp_path)
        await state.set_state(AddTask.waiting_for_overwrite)
        return

    shutil.move(temp_path, final_path)
    await insert_task(task_id, answer)
    await message.answer(f"✅ Задание {task_id} успешно добавлено! Ответ: {answer}", reply_markup=get_main_keyboard())
    await state.clear()


@dp.message(AddTask.waiting_for_overwrite, F.text.lower().in_(['да', 'нет']))
async def confirm_overwrite(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text.lower() == 'да':
        task_id = data['pending_task_id']
        answer = data['pending_answer']
        temp_path = data['pending_temp']
        final_path = os.path.join(IMAGES_DIR, f"{task_id}.jpg")
        shutil.move(temp_path, final_path)
        await insert_task(task_id, answer)
        await message.answer(f"✅ Задание {task_id} обновлено!", reply_markup=get_main_keyboard())
    else:
        temp_path = data.get('pending_temp')
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        await message.answer("❌ Добавление отменено.", reply_markup=get_main_keyboard())
    await state.clear()


# ---------- Функция загрузки SoundCloud ----------
def download_soundcloud_first_result(query: str) -> tuple[str, str, str]:
    import yt_dlp

    with tempfile.TemporaryDirectory() as tmpdir:
        outtmpl = os.path.join(tmpdir, '%(title)s.%(ext)s')
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio',
            'outtmpl': outtmpl,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'default_search': 'soundcloud',
        }
        if 'soundcloud.com' in query:
            search_query = query
        else:
            search_query = f"ytsearch1:soundcloud:{query}"

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(search_query, download=True)
                if info is None:
                    raise Exception("Не удалось получить информацию о треке")
                if 'entries' in info:
                    if not info['entries']:
                        raise Exception("По запросу ничего не найдено")
                    video = info['entries'][0]
                else:
                    video = info

                title = video.get('title', 'Неизвестный трек')
                performer = video.get('uploader', video.get('artist', 'Неизвестный исполнитель'))

                audio_exts = ['.m4a', '.mp3', '.opus', '.ogg', '.wav']
                downloaded_file = None
                for root, dirs, files in os.walk(tmpdir):
                    for f in files:
                        if os.path.splitext(f)[1].lower() in audio_exts:
                            downloaded_file = os.path.join(root, f)
                            break
                    if downloaded_file:
                        break
                if not downloaded_file:
                    all_files = [os.path.join(r, f) for r, _, fs in os.walk(tmpdir) for f in fs]
                    if all_files:
                        downloaded_file = all_files[0]
                    else:
                        raise Exception("Не удалось найти скачанный файл")

                ext = os.path.splitext(downloaded_file)[1]
                final_path = tempfile.mktemp(suffix=ext)
                shutil.copy(downloaded_file, final_path)
                return final_path, title, performer

            except yt_dlp.utils.DownloadError as e:
                raise Exception(f"Ошибка загрузки: {e}")
            except Exception as e:
                raise Exception(f"Ошибка: {e}")


# ---------- Запуск ----------
async def main():
    await init_db()
    print("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())