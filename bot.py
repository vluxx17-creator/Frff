import asyncio
import aiosqlite
import os
import aiohttp
import phonenumbers
import urllib.parse
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, LabeledPrice, PreCheckoutQuery, ContentType, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- КОНФИГУРАЦИЯ ---
TOKEN = '8782789238:AAENc2VrGUNUKQnUbI2SKt79dpJfJKF6UZo'
VK_TOKEN = 'vk1.a.gg0A2uqhaeJR4Q0rQroAOrKxLtlld-zpDhUuNRsLph2tyJZzoyIioGN8vNs_AzCfepKFqTdigONU-ydz1VZnL68Ns7qZ0HcgUhmEOE_F1ZI26awIwunbGfzTpn-xmEEXAueaaBR5lb-ew_z478YoxYuNlAEHHfGBddR9u10-MJae6l1UUC4C3eKWD28ugFy7hhguP-Ihcxsb42Fbq_SPsw'
ADMIN_IDS = [7572936594, 911874462] # Список ID администраторов

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
session = None 

pending_searches = {}

class States(StatesGroup):
    fio, phone, email, vk, ip, ton = State(), State(), State(), State(), State(), State()

# --- ЛОГИРОВАНИЕ ---
async def log_to_db(db_name, data):
    async with aiosqlite.connect(db_name) as db:
        query = "INSERT INTO search_logs (user_id, type, query, date) VALUES (?, ?, ?, ?)" if db_name == "history.db" else "INSERT INTO payments (user_id, username, fio, date) VALUES (?, ?, ?, ?)"
        await db.execute(query, data)
        await db.commit()

# --- МЕНЮ ---
def main_kb(user_id):
    btns = [
        [KeyboardButton(text="👤 ФИО (DEEP SCAN ⭐️)")],
        [KeyboardButton(text="👤 ВК Профиль"), KeyboardButton(text="📞 HLR / Номер")],
        [KeyboardButton(text="🌐 IP Address"), KeyboardButton(text="📧 Email OSINT")],
        [KeyboardButton(text="💎 TON Wallet"), KeyboardButton(text="👤 Профиль")]
    ]
    if user_id in ADMIN_IDS:
        btns.append([KeyboardButton(text="📥 Оплаты"), KeyboardButton(text="📥 Логи")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

# --- ГЕНЕРАТОР ОТЧЕТА ПО ФИО ---
async def generate_fio_report(fio):
    enc = urllib.parse.quote(fio)
    vk_url = f"https://api.vk.com/method/users.search?q={enc}&count=1&fields=bdate,city,domain,status&access_token={VK_TOKEN}&v=5.131"
    ok = f"https://ok.ru/search?st.query={enc}"
    fb = f"https://www.facebook.com/public/{enc.replace(' ', '-')}"
    gos = f"https://www.google.com/search?q=site:fssp.gov.ru+OR+site:nalog.gov.ru+OR+site:sudrf.ru+%22{enc}%22"
    
    async with session.get(vk_url) as r:
        data = await r.json()
        u = data['response']['items'][0] if 'response' in data and data['response']['items'] else {}
        return (
            f"<b>[ 📂 СФОРМИРОВАНО ДОСЬЕ: {fio.upper()} ]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>ДАННЫЕ ВК:</b>\n"
            f"├ ДР: <code>{u.get('bdate','Скрыто')}</code>\n"
            f"├ Город: <code>{u.get('city',{}).get('title','Не найден')}</code>\n"
            f"└ Профиль: vk.com/{u.get('domain', 'id'+str(u.get('id','')))}\n\n"
            f"🌐 <b>СОЦСЕТИ:</b>\n"
            f"├ <a href='{ok}'>Одноклассники</a> | <a href='{fb}'>Facebook</a>\n\n"
            f"🏛 <b>РЕЕСТРЫ РФ (ФССП/ИНН):</b>\n"
            f"└ <a href='{gos}'>ПРОВЕРИТЬ ДОЛГИ И СУДЫ</a>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(m: Message):
    await m.answer("<b>SYSTEM START...</b>\nOSINT Ultimate Ready.\n\nПодпишись: @owhig 👤", reply_markup=main_kb(m.from_user.id), parse_mode="HTML")

@dp.message(F.text == "👤 ФИО (DEEP SCAN ⭐️)")
async def s_fio(m: Message, state: FSMContext):
    await m.answer("📝 <b>Введите ФИО цели:</b>", parse_mode="HTML")
    await state.set_state(States.fio)

@dp.message(States.fio)
async def p_fio(m: Message, state: FSMContext):
    fio = m.text
    if m.from_user.id in ADMIN_IDS:
        await m.answer("🔓 <b>ADMIN BYPASS:</b> Генерирую...")
        await log_to_db("plat.db", (m.from_user.id, m.from_user.username, fio, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        await m.answer(await generate_fio_report(fio), parse_mode="HTML", disable_web_page_preview=True)
    else:
        pending_searches[m.from_user.id] = fio
        await m.answer_invoice(title="FIO SEARCH", description=f"Цель: {fio}", prices=[LabeledPrice(label="15 Stars", amount=15)], payload=f"f_{m.from_user.id}", currency="XTR", start_parameter="fio")
    await state.clear()

@dp.pre_checkout_query()
async def pre_c(q: PreCheckoutQuery): await q.answer(ok=True)

@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def success_p(m: Message):
    fio = pending_searches.get(m.from_user.id, "Неизвестно")
    await log_to_db("plat.db", (m.from_user.id, m.from_user.username, fio, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    await m.answer(await generate_fio_report(fio), parse_mode="HTML", disable_web_page_preview=True)

@dp.message(F.text == "📞 HLR / Номер")
async def s_phone(m: Message, state: FSMContext):
    await m.answer("📞 <b>Введите номер (+7...):</b>", parse_mode="HTML")
    await state.set_state(States.phone)

@dp.message(States.phone)
async def p_phone(m: Message, state: FSMContext):
    await log_to_db("history.db", (m.from_user.id, "PHONE", m.text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    clean = "".join(filter(str.isdigit, m.text))
    report = (f"<b>[ 📱 НОМЕР: +{clean} ]</b>\n"
              f"├ <a href='https://numbuster.com/ru/phone/{clean}'>Теги (NumBuster)</a>\n"
              f"└ <a href='https://mnp.ros-reestr.ru/search?phone={clean}'>Проверка MNP</a>")
    await m.answer(report, parse_mode="HTML", disable_web_page_preview=True)
    await state.clear()

@dp.message(F.text == "📥 Оплаты")
async def d_p(m: Message):
    if m.from_user.id in ADMIN_IDS:
        if os.path.exists("plat.db"): await m.answer_document(FSInputFile("plat.db"))

@dp.message(F.text == "📥 Логи")
async def d_l(m: Message):
    if m.from_user.id in ADMIN_IDS:
        if os.path.exists("history.db"): await m.answer_document(FSInputFile("history.db"))

@dp.message(F.text == "👤 Профиль")
async def prof(m: Message):
    status = "Admin" if m.from_user.id in ADMIN_IDS else "User"
    await m.answer(f"👤 <b>ID:</b> <code>{m.from_user.id}</code>\n<b>Статус:</b> {status}", parse_mode="HTML")

# --- СЕРВЕР И АНТИ-СОН ---
async def handle(r): return web.Response(text="ACTIVE")
async def self_ping():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    while True:
        if url:
            try: async with session.get(url) as r: pass
            except: pass
        await asyncio.sleep(300)

async def main():
    async with aiosqlite.connect("history.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS search_logs (id INTEGER PRIMARY KEY, user_id INTEGER, type TEXT, query TEXT, date TEXT)")
        await db.commit()
    async with aiosqlite.connect("plat.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, user_id INTEGER, username TEXT, fio TEXT, date TEXT)")
        await db.commit()
    
    global session
    session = aiohttp.ClientSession()
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await asyncio.gather(web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080))).start(), dp.start_polling(bot), self_ping())

if __name__ == "__main__":
    asyncio.run(main())
