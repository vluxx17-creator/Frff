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
ADMIN_ID = 7572936594

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
session = None 

pending_searches = {}

class States(StatesGroup):
    fio = State()
    phone = State()
    ip = State()
    email = State()
    ton = State()
    vk = State()

# --- БАЗЫ ДАННЫХ ---
async def log_search(user_id, stype, query):
    async with aiosqlite.connect("history.db") as db:
        await db.execute("INSERT INTO search_logs (user_id, type, query, date) VALUES (?, ?, ?, ?)",
                         (user_id, stype, query, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        await db.commit()

async def log_payment(user_id, username, fio):
    async with aiosqlite.connect("plat.db") as db:
        await db.execute("INSERT INTO payments (user_id, username, fio, date) VALUES (?, ?, ?, ?)",
                         (user_id, username, fio, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        await db.commit()

# --- КЛАВИАТУРА ---
def main_kb(user_id):
    btns = [
        [KeyboardButton(text="👤 ФИО (15 ⭐️)")],
        [KeyboardButton(text="📧 Email"), KeyboardButton(text="📞 Номер")],
        [KeyboardButton(text="🌐 IP"), KeyboardButton(text="👤 ВК")],
        [KeyboardButton(text="💎 TON"), KeyboardButton(text="👤 Профиль")]
    ]
    if user_id == ADMIN_ID:
        btns.append([KeyboardButton(text="📥 База оплат"), KeyboardButton(text="📥 Логи поиска")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

# --- DEEP OSINT LOGIC ---
async def get_fio_report(fio):
    enc = urllib.parse.quote(fio)
    vk_url = f"https://api.vk.com/method/users.search?q={enc}&count=1&fields=bdate,city,country,site,domain,home_phone&access_token={VK_TOKEN}&v=5.131"
    
    # OSINT Links
    ok = f"https://ok.ru/search?st.query={enc}"
    fb = f"https://www.facebook.com/public/{enc.replace(' ', '-')}"
    inst = f"https://www.google.com/search?q=site:instagram.com+%22{enc}%22"
    linked = f"https://www.google.com/search?q=site:linkedin.com/in+%22{enc}%22"
    
    # Government/Court/FSSP Dorks
    gos = f"https://www.google.com/search?q=site:fssp.gov.ru+OR+site:nalog.gov.ru+OR+site:sudrf.ru+%22{enc}%22"

    async with session.get(vk_url) as r:
        data = await r.json()
        u = data['response']['items'][0] if 'response' in data and data['response']['items'] else {}
        
        return (
            f"🔍 <b>МАКСИМАЛЬНЫЙ ОТЧЕТ: {fio}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>ДАННЫЕ ИЗ ВК:</b>\n"
            f"├ ДР: {u.get('bdate', 'Скрыто')}\n"
            f"├ Город: {u.get('city', {}).get('title', 'Не указан')}\n"
            f"├ Контакт: <code>{u.get('site', 'Скрыто')}</code>\n"
            f"└ Ссылка: vk.com/{u.get('domain', 'id'+str(u.get('id','')))}\n\n"
            f"📱 <b>СОЦСЕТИ (OSINT):</b>\n"
            f"├ <a href='{ok}'>Одноклассники</a> | <a href='{fb}'>Facebook</a>\n"
            f"└ <a href='{inst}'>Instagram</a> | <a href='{linked}'>LinkedIn</a>\n\n"
            f"🏛 <b>ГОСРЕЕСТРЫ РФ (ФССП/СУДЫ/ИНН):</b>\n"
            f"└ <a href='{gos}'>ПОИСК ДОЛГОВ И ДЕЛ</a>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <i>Лучше чем Шерлок | @searchHams_bot</i>"
        )

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(m: Message):
    await m.answer("Приветствую в @searchHams_bot\nТут есть поиск абсолютно по всему.\n\nПодпишись на @owhig 👤", reply_markup=main_kb(m.from_user.id))

@dp.message(F.text == "📥 База оплат")
async def db_p(m: Message):
    if m.from_user.id == ADMIN_ID and os.path.exists("plat.db"):
        await m.answer_document(FSInputFile("plat.db"))

@dp.message(F.text == "📥 Логи поиска")
async def db_h(m: Message):
    if m.from_user.id == ADMIN_ID and os.path.exists("history.db"):
        await m.answer_document(FSInputFile("history.db"))

@dp.message(F.text == "👤 ФИО (15 ⭐️)")
async def s_fio(m: Message, state: FSMContext):
    await m.answer("👤 <b>Введите ФИО для пробива:</b>", parse_mode="HTML")
    await state.set_state(States.fio)

@dp.message(States.fio)
async def p_fio(m: Message, state: FSMContext):
    fio = m.text
    if m.from_user.id == ADMIN_ID:
        await log_payment(m.from_user.id, m.from_user.username, fio)
        await m.answer(await get_fio_report(fio), parse_mode="HTML", disable_web_page_preview=True)
    else:
        pending_searches[m.from_user.id] = fio
        await m.answer_invoice(title="Deep Search ФИО", description=f"Запрос: {fio}", prices=[LabeledPrice(label="15 Stars", amount=15)], payload=f"f_{m.from_user.id}", currency="XTR", start_parameter="fio")
    await state.clear()

@dp.pre_checkout_query()
async def pre_c(q: PreCheckoutQuery): await q.answer(ok=True)

@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def success_p(m: Message):
    fio = pending_searches.get(m.from_user.id, "Неизвестно")
    await log_payment(m.from_user.id, m.from_user.username, fio)
    await m.answer(await get_fio_report(fio), parse_mode="HTML", disable_web_page_preview=True)

@dp.message(F.text == "📧 Email")
async def s_e(m: Message, state: FSMContext):
    await m.answer("📧 Введите Email:")
    await state.set_state(States.email)

@dp.message(States.email)
async def p_e(m: Message, state: FSMContext):
    await log_search(m.from_user.id, "EMAIL", m.text)
    report = (
        f"🔍 <b>OSINT ПО EMAIL: {m.text}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>ГДЕ ЗАРЕГИСТРИРОВАН:</b>\n"
        f"└ <a href='https://epieos.com/?q={m.text}'>Проверить аккаунты (Epieos)</a>\n"
        f"└ <a href='https://intelx.io/?s={m.text}'>Поиск в утечках (IntelX)</a>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    await m.answer(report, parse_mode="HTML", disable_web_page_preview=True)
    await state.clear()

@dp.message(F.text == "📞 Номер")
async def s_p(m: Message, state: FSMContext):
    await m.answer("📞 Введите номер (+7...):")
    await state.set_state(States.phone)

@dp.message(States.phone)
async def p_p(m: Message, state: FSMContext):
    await log_search(m.from_user.id, "PHONE", m.text)
    try:
        parsed = phonenumbers.parse(m.text)
        await m.answer(f"📞 <b>ИНФО:</b> {m.text}\n└ Код страны: {parsed.country_code}", parse_mode="HTML")
    except: await m.answer("❌ Ошибка формата")
    await state.clear()

@dp.message(F.text == "🌐 IP")
async def s_ip(m: Message, state: FSMContext):
    await m.answer("🌐 Введите IP:")
    await state.set_state(States.ip)

@dp.message(States.ip)
async def p_ip(m: Message, state: FSMContext):
    await log_search(m.from_user.id, "IP", m.text)
    async with session.get(f"http://ip-api.com/json/{m.text}") as r:
        d = await r.json()
        if d.get('status') == 'success':
            await m.answer(f"🌐 <b>IP:</b> {m.text}\n├ Страна: {d['country']}\n└ Провайдер: {d['isp']}", parse_mode="HTML")
    await state.clear()

@dp.message(F.text == "👤 ВК")
async def s_vk(m: Message, state: FSMContext):
    await m.answer("👤 Введите ссылку или ID ВК:")
    await state.set_state(States.vk)

@dp.message(States.vk)
async def p_vk(m: Message, state: FSMContext):
    await log_search(m.from_user.id, "VK", m.text)
    await m.answer(f"🔎 Информация по ВК профилю {m.text} собирается...")
    await state.clear()

@dp.message(F.text == "👤 Профиль")
async def prof(m: Message):
    await m.answer(f"👤 <b>ВАШ ПРОФИЛЬ:</b>\n├ ID: <code>{m.from_user.id}</code>\n└ Username: @{m.from_user.username}", parse_mode="HTML")

# --- СЕРВЕР И АНТИ-СОН ---
async def handle(r): return web.Response(text="OSINT MAX IS ACTIVE")
async def self_ping():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    while url:
        try:
            async with session.get(url) as r: pass
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
    
    port = int(os.environ.get("PORT", 8080))
    await asyncio.gather(web.TCPSite(runner, '0.0.0.0', port).start(), dp.start_polling(bot), self_ping())

if __name__ == "__main__":
    asyncio.run(main())
