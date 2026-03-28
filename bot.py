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
ADMIN_ID = 7572936594 # Твой ID, тебе поиск будет бесплатно

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
session = None 

# Временное хранилище запросов
pending_searches = {}

class States(StatesGroup):
    fio = State()
    phone = State()
    ip = State()

# --- ФУНКЦИЯ ЗАПИСИ В БД ОПЛАТ ---
async def log_payment(user_id, username, fio):
    async with aiosqlite.connect("plat.db") as db:
        await db.execute("INSERT INTO payments (user_id, username, fio, date) VALUES (?, ?, ?, ?)",
                         (user_id, username, fio, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        await db.commit()

# --- МЕНЮ ---
def main_kb(user_id):
    btns = [
        [KeyboardButton(text="👤 ФИО (15 ⭐️)")],
        [KeyboardButton(text="📞 Номер"), KeyboardButton(text="🌐 IP")],
        [KeyboardButton(text="👤 Профиль")]
    ]
    if user_id == ADMIN_ID:
        btns.append([KeyboardButton(text="📥 База оплат")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

# --- ПРИВЕТСТВИЕ ---
@dp.message(Command("start"))
async def cmd_start(m: Message):
    text = (
        "Приветствую в @searchHams_bot\n"
        "Тут есть поиск абсолютно по всему (VK, OK, FB, Госуслуги)\n"
        "Лучше чем Шерлок\n\n"
        "Подпишись на @owhig 👤"
    )
    await m.answer(text, reply_markup=main_kb(m.from_user.id))

# --- АДМИНКА: СКАЧАТЬ БАЗУ ---
@dp.message(F.text == "📥 База оплат")
async def send_db(m: Message):
    if m.from_user.id == ADMIN_ID:
        if os.path.exists("plat.db"):
            await m.answer_document(FSInputFile("plat.db"), caption="📂 Актуальная база оплаченных запросов.")
        else:
            await m.answer("❌ База пока пуста.")

# --- ОБЩАЯ ФУНКЦИЯ ВЫДАЧИ ОТЧЕТА ---
async def get_osint_report(fio):
    encoded_fio = urllib.parse.quote(fio)
    vk_url = f"https://api.vk.com/method/users.search?q={encoded_fio}&count=1&fields=bdate,city,country,site,domain&access_token={VK_TOKEN}&v=5.131"
    ok_link = f"https://ok.ru/search?st.query={encoded_fio}"
    fb_link = f"https://www.facebook.com/public/{encoded_fio.replace(' ', '-')}"
    gos_link = f"https://www.google.com/search?q=site:fssp.gov.ru+OR+site:nalog.gov.ru+OR+site:sudrf.ru+%22{encoded_fio}%22"

    async with session.get(vk_url) as r:
        data = await r.json()
        u = data['response']['items'][0] if 'response' in data and data['response']['items'] else {}
        return (
            f"✅ <b>ОТЧЕТ ПО ФИО: {fio}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>ДАННЫЕ ИЗ ВК:</b>\n"
            f"├ ДР: {u.get('bdate', 'Скрыто')}\n"
            f"├ Город: {u.get('city', {}).get('title', 'Не указан')}\n"
            f"├ Контакты: {u.get('site', 'Не найдены')}\n"
            f"└ Профиль: vk.com/{u.get('domain', 'id'+str(u.get('id','')))}\n\n"
            f"📱 <b>ДРУГИЕ СОЦСЕТИ:</b>\n"
            f"├ OK: <a href='{ok_link}'>Открыть OK.ru</a>\n"
            f"└ FB: <a href='{fb_link}'>Открыть Facebook</a>\n\n"
            f"🏛 <b>ГОСРЕЕСТРЫ (ФССП/СУДЫ/ИНН):</b>\n"
            f"└ <a href='{gos_link}'>Проверить в реестрах РФ</a>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <i>Бот @searchHams_bot — Лучше чем Шерлок</i>"
        )

# --- МОДУЛЬ ФИО + ЛОГИКА ОПЛАТЫ/АДМИНА ---
@dp.message(F.text == "👤 ФИО (15 ⭐️)")
async def s_fio(m: Message, state: FSMContext):
    await m.answer("👤 <b>ВВЕДИТЕ ФИО ЦЕЛИ:</b>", parse_mode="HTML")
    await state.set_state(States.fio)

@dp.message(States.fio)
async def p_fio_request(m: Message, state: FSMContext):
    fio_query = m.text
    user_id = m.from_user.id
    
    # ПРОВЕРКА НА АДМИНА (БЕСПЛАТНО)
    if user_id == ADMIN_ID:
        await m.answer("👑 <b>РЕЖИМ АДМИНИСТРАТОРА:</b> Поиск бесплатно...")
        report = await get_osint_report(fio_query)
        await log_payment(user_id, m.from_user.username, fio_query)
        await m.answer(report, parse_mode="HTML", disable_web_page_preview=True)
    else:
        # ПЛАТНО ДЛЯ ОСТАЛЬНЫХ
        pending_searches[user_id] = fio_query
        prices = [LabeledPrice(label="Deep Search (ФИО)", amount=15)]
        await m.answer_invoice(
            title="Оплата OSINT-отчета",
            description=f"Поиск данных для: {fio_query}",
            prices=prices,
            payload=f"fio_{user_id}",
            currency="XTR",
            start_parameter="fio_search"
        )
    await state.clear()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_pay(m: Message):
    user_id = m.from_user.id
    fio = pending_searches.get(user_id, "Неизвестно")
    await log_payment(user_id, m.from_user.username, fio)
    report = await get_osint_report(fio)
    await m.answer(report, parse_mode="HTML", disable_web_page_preview=True)

# --- ДРУГИЕ МОДУЛИ ---
@dp.message(F.text == "📞 Номер")
async def s_phone(m: Message, state: FSMContext):
    await m.answer("📞 Введите номер (+7...):")
    await state.set_state(States.phone)

@dp.message(States.phone)
async def p_phone(m: Message, state: FSMContext):
    try:
        p = phonenumbers.parse(m.text)
        await m.answer(f"📞 <b>ИНФО:</b> {m.text}\n└ Страна: {p.country_code}", parse_mode="HTML")
    except: await m.answer("❌ Ошибка.")
    await state.clear()

@dp.message(F.text == "🌐 IP")
async def s_ip(m: Message, state: FSMContext):
    await m.answer("🌐 Введите IP:")
    await state.set_state(States.ip)

@dp.message(States.ip)
async def p_ip(m: Message, state: FSMContext):
    async with session.get(f"http://ip-api.com/json/{m.text}") as r:
        d = await r.json()
        if d.get('status') == 'success':
            await m.answer(f"🌐 <b>IP: {m.text}</b>\n└ Страна: {d['country']}", parse_mode="HTML")
    await state.clear()

@dp.message(F.text == "👤 Профиль")
async def cmd_profile(m: Message):
    await m.answer(f"👤 Твой ID: <code>{m.from_user.id}</code>\nТвой Username: @{m.from_user.username}", parse_mode="HTML")

# --- СИСТЕМА АНТИ-СНА ---
async def handle(r): return web.Response(text="BOT ACTIVE", status=200)

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
