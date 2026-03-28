import asyncio
import aiosqlite
import os
import aiohttp
import phonenumbers
import urllib.parse
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, LabeledPrice, PreCheckoutQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- CONFIGURATION ---
TOKEN = '8782789238:AAENc2VrGUNUKQnUbI2SKt79dpJfJKF6UZo'
VK_TOKEN = 'vk1.a.gg0A2uqhaeJR4Q0rQroAOrKxLtlld-zpDhUuNRsLph2tyJZzoyIioGN8vNs_AzCfepKFqTdigONU-ydz1VZnL68Ns7qZ0HcgUhmEOE_F1ZI26awIwunbGfzTpn-xmEEXAueaaBR5lb-ew_z478YoxYuNlAEHHfGBddR9u10-MJae6l1UUC4C3eKWD28ugFy7hhguP-Ihcxsb42Fbq_SPsw'
ADMIN_IDS = [7572936594, 911874462]

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
session = None 
pending_searches = {}

class States(StatesGroup):
    fio = State()
    phone = State()
    vk = State()
    ip = State()
    ton = State()

# --- DATABASE ---
async def log_to_db(db_name, data):
    async with aiosqlite.connect(db_name) as db:
        q = "INSERT INTO search_logs (user_id, type, query, date) VALUES (?, ?, ?, ?)" if db_name == "history.db" else "INSERT INTO payments (user_id, username, fio, date) VALUES (?, ?, ?, ?)"
        await db.execute(q, data)
        await db.commit()

# --- KEYBOARDS ---
def main_kb(user_id):
    btns = [
        [KeyboardButton(text="ð¤ Ð¤ÐÐ (DEEP SCAN â­ï¸)")],
        [KeyboardButton(text="ð¤ ÐÐ ÐÑÐ¾ÑÐ¸Ð»Ñ"), KeyboardButton(text="ð HLR / ÐÐ¾Ð¼ÐµÑ")],
        [KeyboardButton(text="ð IP Address"), KeyboardButton(text="ð TON Wallet")],
        [KeyboardButton(text="ð¤ ÐÑÐ¾ÑÐ¸Ð»Ñ")]
    ]
    if user_id in ADMIN_IDS:
        btns.append([KeyboardButton(text="ð¥ ÐÐ¿Ð»Ð°ÑÑ"), KeyboardButton(text="ð¥ ÐÐ¾Ð³Ð¸")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

# --- SEARCH MODULES ---
async def get_fio_report(fio):
    enc = urllib.parse.quote(fio)
    vk_url = f"https://api.vk.com/method/users.search?q={enc}&count=1&fields=bdate,city,domain&access_token={VK_TOKEN}&v=5.131"
    async with session.get(vk_url) as r:
        v = await r.json()
        u = v['response']['items'][0] if 'response' in v and v['response']['items'] else {}
        return (f"<b>[ ð ÐÐÐ¡Ð¬Ð: {fio.upper()} ]</b>\n"
                f"â ÐÐ: <code>{u.get('bdate','-')}</code>, {u.get('city',{}).get('title','-')}\n"
                f"â ÐÑÐ¾ÑÐ¸Ð»Ñ: vk.com/{u.get('domain','id')}\n"
                f"â <a href='https://fssp.gov.ru/iss/ip?is%5Blast_name%5D={fio.split()[0]}'>Ð¤Ð¡Ð¡Ð (ÐÐ¾Ð»Ð³Ð¸)</a>")

# --- HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(m: Message):
    await m.answer("<b>бета тест готов к твоему использованию</b>", reply_markup=main_kb(m.from_user.id), parse_mode="HTML")

@dp.message(F.text == "ð¤ Ð¤ÐÐ (DEEP SCAN â­ï¸)")
async def s_f(m: Message, state: FSMContext):
    await m.answer("ÐÐ²ÐµÐ´Ð¸ÑÐµ Ð¤ÐÐ:")
    await state.set_state(States.fio)

@dp.message(States.fio)
async def p_f(m: Message, state: FSMContext):
    fio = m.text
    if m.from_user.id in ADMIN_IDS:
        await m.answer(await get_fio_report(fio), parse_mode="HTML")
    else:
        pending_searches[m.from_user.id] = fio
        await m.answer_invoice(title="SEARCH", description=fio, prices=[LabeledPrice(label="XTR", amount=15)], payload="pay", currency="XTR")
    await state.clear()

@dp.pre_checkout_query()
async def pre_c(q: PreCheckoutQuery): await q.answer(ok=True)

@dp.message(F.successful_payment)
async def pay_ok(m: Message):
    fio = pending_searches.get(m.from_user.id, "Error")
    await m.answer(await get_fio_report(fio), parse_mode="HTML")

@dp.message(F.text == "ð¥ ÐÐ¿Ð»Ð°ÑÑ")
async def d_p(m: Message):
    if m.from_user.id in ADMIN_IDS and os.path.exists("plat.db"):
        await m.answer_document(FSInputFile("plat.db"))

@dp.message(F.text == "ð¥ ÐÐ¾Ð³Ð¸")
async def d_l(m: Message):
    if m.from_user.id in ADMIN_IDS and os.path.exists("history.db"):
        await m.answer_document(FSInputFile("history.db"))

@dp.message(F.text == "ð¤ ÐÑÐ¾ÑÐ¸Ð»Ñ")
async def prof(m: Message):
    status = "Admin" if m.from_user.id in ADMIN_IDS else "User"
    await m.answer(f"ID: {m.from_user.id}\nStatus: {status}")

# --- WEB SERVER ---
async def handle(r): return web.Response(text="OK")
async def self_ping():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    while True:
        if url:
            try:
                async with session.get(url) as r: pass
            except: pass
        await asyncio.sleep(300)

async def main():
    async with aiosqlite.connect("history.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS search_logs (id INTEGER PRIMARY KEY, user_id INTEGER, type TEXT, query TEXT, date TEXT)")
    async with aiosqlite.connect("plat.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, user_id INTEGER, username TEXT, fio TEXT, date TEXT)")
    
    global session
    session = aiohttp.ClientSession()
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    
    await asyncio.gather(
        web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080))).start(),
        dp.start_polling(bot),
        self_ping()
    )

if __name__ == "__main__":
    asyncio.run(main())
