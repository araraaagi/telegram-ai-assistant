
import logging
import sqlite3
import aiohttp
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InputFile
from datetime import datetime, timedelta
import asyncio
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
DB_NAME = "assistant.db"
DAILY_CHECK_HOUR = 9

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

logging.basicConfig(level=logging.INFO)

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        content TEXT,
                        remind_time TEXT,
                        is_daily INTEGER,
                        is_done INTEGER DEFAULT 0
                    )""")
        conn.commit()

async def ask_openrouter(prompt):
    logging.info("🧠 Отправка запроса в OpenRouter...")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://t.me/araragiai_bot",
        "X-Title": "AI Telegram Assistant",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "qwen:chat",
        "messages": [
            {"role": "system", "content": "Ты персональный Telegram-ассистент. Отвечай по делу, кратко и понятно."},
            {"role": "user", "content": prompt}
        ]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            logging.info(f"📡 Status: {response.status}")
            res = await response.text()
            logging.info(f"📩 Response: {res}")
            if response.status == 200:
                result = await response.json()
                return result['choices'][0]['message']['content']
            else:
                raise Exception("OpenRouter error")

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

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply("👋 Привет! Я твой OpenRouter-ассистент. Просто пиши:\n— вопросы\n— задачи\n— мысли\nЯ всё запомню и помогу!")

@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_text_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    logging.info(f"Received from {user_id}: {text}")

    if "напомни" in text.lower():
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            remind_time = datetime.now() + timedelta(hours=1)
            c.execute("INSERT INTO tasks (user_id, content, remind_time, is_daily) VALUES (?, ?, ?, ?)",
                      (user_id, text, remind_time.isoformat(), 0))
            conn.commit()
        await message.answer("🕒 Напоминание добавлено!")

    elif "каждый день" in text.lower():
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO tasks (user_id, content, remind_time, is_daily) VALUES (?, ?, ?, ?)",
                      (user_id, text, None, 1))
            conn.commit()
        await message.answer("📆 Ежедневная задача сохранена!")

    elif "документ" in text.lower():
        gpt_response = await ask_openrouter(text)
        with open("doc.txt", "w", encoding="utf-8") as f:
            f.write(gpt_response)
        await message.answer_document(InputFile("doc.txt"))

    else:
        try:
            gpt_response = await ask_openrouter(text)
            await message.answer(gpt_response)
        except Exception as e:
            logging.error(f"OpenRouter ERROR: {e}")
            await message.answer("⚠️ Ошибка при обращении к OpenRouter.")

if __name__ == "__main__":
    init_db()
    loop = asyncio.get_event_loop()
    loop.create_task(daily_check())
    executor.start_polling(dp, skip_updates=True)
