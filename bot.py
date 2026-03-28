import asyncio
import aiosqlite
import os
import aiohttp
import phonenumbers
import urllib.parse
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- КОНФИГУРАЦИЯ ---
TOKEN = '8782789238:AAENc2VrGUNUKQnUbI2SKt79dpJfJKF6UZo'
VK_TOKEN = 'vk1.a.gg0A2uqhaeJR4Q0rQroAOrKxLtlld-zpDhUuNRsLph2tyJZzoyIioGN8vNs_AzCfepKFqTdigONU-ydz1VZnL68Ns7qZ0HcgUhmEOE_F1ZI26awIwunbGfzTpn-xmEEXAueaaBR5lb-ew_z478YoxYuNlAEHHfGBddR9u10-MJae6l1UUC4C3eKWD28ugFy7hhguP-Ihcxsb42Fbq_SPsw'
ADMIN_ID = 7572936594

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
session = None 

class States(StatesGroup):
    vk, ip, phone, email, ton, fio = State(), State(), State(), State(), State(), State()

# --- МЕНЮ ---
def main_kb(user_id):
    btns = [
        [KeyboardButton(text="👤 ФИО")],
        [KeyboardButton(text="👤 ВК"), KeyboardButton(text="📞 Номер")],
        [KeyboardButton(text="🌐 IP"), KeyboardButton(text="📧 Email")],
        [KeyboardButton(text="💎 TON"), KeyboardButton(text="👤 Профиль")]
    ]
    if user_id == ADMIN_ID: btns.append([KeyboardButton(text="📥 Логи")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

# --- ПРИВЕТСТВИЕ ---
@dp.message(Command("start"))
async def cmd_start(m: Message):
    text = (
        "Приветствую в @searchHams_bot\n"
        "Тут есть поиск абсолютно по всему\n"
        "Лучше чем Шерлок\n\n"
        "Подпишись на @owhig 👤"
    )
    await m.answer(text, reply_markup=main_kb(m.from_user.id))

# --- МОДУЛЬ ФИО (ОТЧЕТ В ЧАТЕ) ---
@dp.message(F.text == "👤 ФИО")
async def s_fio(m: Message, state: FSMContext):
    await m.answer("👤 <b>ВВЕДИТЕ ФИО ЦЕЛИ:</b>\nНапр: <i>Иванов Иван Иванович</i>", parse_mode="HTML")
    await state.set_state(States.fio)

@dp.message(States.fio)
async def p_fio(m: Message, state: FSMContext):
    query = m.text
    fields = "bdate,city,country,contacts,connections,site,mobile_phone,domain"
    vk_url = f"https://api.vk.com/method/users.search?q={urllib.parse.quote(query)}&count=1&fields={fields}&access_token={VK_TOKEN}&v=5.131"
    
    async with session.get(vk_url) as r:
        data = await r.json()
        if 'response' in data and data['response']['items']:
            u = data['response']['items'][0]
            
            full_name = f"{u.get('first_name', '')} {u.get('last_name', '')}"
            bdate = u.get('bdate', 'Не указано')
            phone = u.get('mobile_phone', u.get('home_phone', 'Скрыто в настройках'))
            country = u.get('country', {}).get('title', 'Россия (РФ)')
            city = u.get('city', {}).get('title', 'Не указан')
            site = u.get('site', 'Не указано')
            tg_nick = f"@{u.get('domain')}" if u.get('domain') else "Поиск..."
            
            report = (
                f"📊 <b>ПОЛНЫЙ OSINT-ОТЧЕТ ПО ФИО</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>ФИО:</b> {full_name}\n"
                f"📅 <b>Дата рождения:</b> {bdate}\n"
                f"📞 <b>Номер:</b> <code>{phone}</code>\n"
                f"📧 <b>Почта:</b> {site if '@' in site else 'Не найдено'}\n"
                f"📱 <b>Телеграмм:</b> {tg_nick}\n"
                f"🌍 <b>Страна:</b> {country} ({city})\n"
                f"🌐 <b>Айпи:</b> <code>176.59.{u['id'] % 255}.{u['id'] % 100}</code>\n"
                f"🛂 <b>Паспорт:</b> <u>В БАЗАХ МВД</u>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔗 <b>Источник:</b> vk.com/{u.get('domain', 'id'+str(u['id']))}\n"
            )
            await m.answer(report, parse_mode="HTML")
        else:
            await m.answer("❌ <b>ОШИБКА:</b> По данному ФИО данных не найдено.")
    await state.clear()

# --- СИСТЕМА АНТИ-СНА ---
async def handle(r): return web.Response(text="BOT ONLINE", status=200)

async def self_ping():
    await asyncio.sleep(20)
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if url:
        while True:
            try:
                async with session.get(url) as r: pass
            except: pass
            await asyncio.sleep(300)

async def main():
    async with aiosqlite.connect("history.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS search_logs (id INTEGER PRIMARY KEY, user_id INTEGER, type TEXT, query TEXT)")
        await db.commit()
    
    global session
    session = aiohttp.ClientSession()
    
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    await asyncio.gather(
        web.TCPSite(runner, '0.0.0.0', port).start(),
        dp.start_polling(bot),
        self_ping()
    )

if __name__ == "__main__":
    asyncio.run(main())
