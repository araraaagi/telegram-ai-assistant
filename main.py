
import logging
import sqlite3
import openai
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InputFile
from datetime import datetime, timedelta
import asyncio
import speech_recognition as sr
import os
from pydub import AudioSegment

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DB_NAME = "assistant.db"
DAILY_CHECK_HOUR = 9

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

logging.basicConfig(level=logging.INFO)

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        content TEXT,
                        remind_time TEXT,
                        is_daily INTEGER,
                        is_done INTEGER DEFAULT 0
                    )''')
        conn.commit()

async def ask_gpt(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Ты персональный ассистент. Пиши чётко, кратко, понятно."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=500
    )
    return response.choices[0].message.content.strip()

async def daily_check():
    while True:
        now = datetime.now()
        if now.hour == DAILY_CHECK_HOUR and now.minute < 5:
            with sqlite3.connect(DB_NAME) as conn:
                c = conn.cursor()
                c.execute("SELECT user_id, content FROM tasks WHERE is_daily = 1")
                tasks = c.fetchall()
                for user_id, content in tasks:
                    await bot.send_message(user_id, f"👋 Утро! Сегодня запланировано: {content}")
        await asyncio.sleep(300)

@dp.message_handler(content_types=types.ContentType.VOICE)
async def handle_voice(message: types.Message):
    file_info = await bot.get_file(message.voice.file_id)
    downloaded_file = await bot.download_file(file_info.file_path)

    with open("audio.ogg", "wb") as f:
        f.write(downloaded_file.read())

    AudioSegment.from_ogg("audio.ogg").export("audio.wav", format="wav")
    recognizer = sr.Recognizer()
    with sr.AudioFile("audio.wav") as source:
        audio_data = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio_data, language="ru-RU")
            await handle_text_message(types.Message(
                message_id=message.message_id,
                from_user=message.from_user,
                chat=message.chat,
                date=message.date,
                text=text
            ))
        except sr.UnknownValueError:
            await message.reply("Не смог разобрать голосовое 😕")

@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_text_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip().lower()

    if "напомни" in text:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            remind_time = datetime.now() + timedelta(hours=1)
            c.execute("INSERT INTO tasks (user_id, content, remind_time, is_daily) VALUES (?, ?, ?, ?)",
                      (user_id, text, remind_time.isoformat(), 0))
            conn.commit()
        await message.answer("🕒 Напоминание добавлено!")

    elif "каждый день" in text:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO tasks (user_id, content, remind_time, is_daily) VALUES (?, ?, ?, ?)",
                      (user_id, text, None, 1))
            conn.commit()
        await message.answer("📆 Ежедневная задача сохранена!")

    elif "документ" in text:
        gpt_response = await ask_gpt(text)
        with open("doc.txt", "w", encoding="utf-8") as f:
            f.write(gpt_response)
        await message.answer_document(InputFile("doc.txt"))

    else:
        await message.answer("Принял! Записал в базу. Если это задача — не забуду 💾")

if __name__ == "__main__":
    init_db()
    loop = asyncio.get_event_loop()
    loop.create_task(daily_check())
    executor.start_polling(dp, skip_updates=True)
