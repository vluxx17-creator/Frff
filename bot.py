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

# --- КОНФИГУРАЦИЯ ---
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

# --- БАЗА ДАННЫХ ---
async def log_to_db(db_name, data):
    async with aiosqlite.connect(db_name) as db:
        q = "INSERT INTO search_logs (user_id, type, query, date) VALUES (?, ?, ?, ?)" if db_name == "history.db" else "INSERT INTO payments (user_id, username, fio, date) VALUES (?, ?, ?, ?)"
        await db.execute(q, data)
        await db.commit()

# --- КЛАВИАТУРА ---
def main_kb(user_id):
    btns = [
        [KeyboardButton(text="👤 ФИО (ГЛУБОКИЙ ПОИСК ⭐️)")],
        [KeyboardButton(text="👤 ВК Профиль"), KeyboardButton(text="📞 HLR / Номер")],
        [KeyboardButton(text="🌐 IP Адрес"), KeyboardButton(text="💎 TON Кошелек")],
        [KeyboardButton(text="👤 Мой Профиль")]
    ]
    if user_id in ADMIN_IDS:
        btns.append([KeyboardButton(text="📥 База Оплат"), KeyboardButton(text="📥 Логи Поиска")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

# --- МОДУЛИ ПОИСКА ---
async def get_fio_report(fio):
    enc = urllib.parse.quote(fio)
    vk_url = f"https://api.vk.com/method/users.search?q={enc}&count=1&fields=bdate,city,domain&access_token={VK_TOKEN}&v=5.131"
    async with session.get(vk_url) as r:
        v = await r.json()
        u = v['response']['items'][0] if 'response' in v and v['response']['items'] else {}
        return (f"<b>[ 📂 СФОРМИРОВАНО ДОСЬЕ: {fio.upper()} ]</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>ДАННЫЕ ВК:</b>\n"
                f"├ Дата рожд.: <code>{u.get('bdate','скрыто')}</code>\n"
                f"├ Город: <code>{u.get('city',{}).get('title','не указан')}</code>\n"
                f"└ Ссылка: vk.com/{u.get('domain','id')}\n\n"
                f"🏛 <b>РЕЕСТРЫ:</b>\n"
                f"└ <a href='https://fssp.gov.ru/iss/ip?is%5Blast_name%5D={fio.split()[0]}'>Проверить долги (ФССП)</a>\n"
                f"━━━━━━━━━━━━━━━━━━━━")

# --- ОБРАБОТЧИКИ (HANDLERS) ---
@dp.message(Command("start"))
async def cmd_start(m: Message):
    await m.answer("<b>СИСТЕМА OSINT ЗАПУЩЕНА</b>\nВыберите нужный модуль в меню ниже.\n\nАвтор: @owhig 👤", reply_markup=main_kb(m.from_user.id), parse_mode="HTML")

@dp.message(F.text == "👤 ФИО (ГЛУБОКИЙ ПОИСК ⭐️)")
async def s_f(m: Message, state: FSMContext):
    await m.answer("📝 <b>Введите ФИО цели для поиска:</b>", parse_mode="HTML")
    await state.set_state(States.fio)

@dp.message(States.fio)
async def p_f(m: Message, state: FSMContext):
    fio = m.text
    if m.from_user.id in ADMIN_IDS:
        await m.answer("🔓 <b>ДОСТУП АДМИНА:</b> Генерирую отчет бесплатно...")
        await m.answer(await get_fio_report(fio), parse_mode="HTML", disable_web_page_preview=True)
    else:
        pending_searches[m.from_user.id] = fio
        await m.answer_invoice(
            title="ПОИСК ПО ФИО",
            description=f"Генерация полного отчета по: {fio}",
            prices=[LabeledPrice(label="Звезды Telegram", amount=15)],
            payload="pay_fio",
            currency="XTR"
        )
    await state.clear()

@dp.pre_checkout_query()
async def pre_c(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def pay_ok(m: Message):
    fio = pending_searches.get(m.from_user.id, "Ошибка")
    await log_to_db("plat.db", (m.from_user.id, m.from_user.username, fio, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    await m.answer("✅ <b>Оплата прошла!</b> Формирую досье...")
    await m.answer(await get_fio_report(fio), parse_mode="HTML", disable_web_page_preview=True)

@dp.message(F.text == "📞 HLR / Номер")
async def s_p(m: Message, state: FSMContext):
    await m.answer("📞 <b>Введите номер телефона (+7...):</b>", parse_mode="HTML")
    await state.set_state(States.phone)

@dp.message(States.phone)
async def p_p(m: Message, state: FSMContext):
    clean = "".join(filter(str.isdigit, m.text))
    await log_to_db("history.db", (m.from_user.id, "PHONE", clean, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    report = (f"<b>[ 📱 НОМЕР: +{clean} ]</b>\n"
              f"├ <a href='https://numbuster.com/ru/phone/{clean}'>Теги (NumBuster)</a>\n"
              f"└ <a href='https://mnp.ros-reestr.ru/search?phone={clean}'>Проверка MNP (Оператор)</a>")
    await m.answer(report, parse_mode="HTML", disable_web_page_preview=True)
    await state.clear()

@dp.message(F.text == "📥 База Оплат")
async def d_p(m: Message):
    if m.from_user.id in ADMIN_IDS and os.path.exists("plat.db"):
        await m.answer_document(FSInputFile("plat.db"), caption="📁 База успешных оплат")

@dp.message(F.text == "📥 Логи Поиска")
async def d_l(m: Message):
    if m.from_user.id in ADMIN_IDS and os.path.exists("history.db"):
        await m.answer_document(FSInputFile("history.db"), caption="📁 Логи всех запросов")

@dp.message(F.text == "👤 Мой Профиль")
async def prof(m: Message):
    status = "👑 Администратор" if m.from_user.id in ADMIN_IDS else "👤 Пользователь"
    await m.answer(f"👤 <b>Ваш Профиль:</b>\n\n🆔 ID: <code>{m.from_user.id}</code>\n📊 Статус: {status}", parse_mode="HTML")

# --- СЕРВЕР И ПИНГ ---
async def handle(r): return web.Response(text="БОТ АКТИВЕН")
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
