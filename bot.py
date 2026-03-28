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
    fio, phone, ip, vk = State(), State(), State(), State()

# --- ЛОГИРОВАНИЕ ---
async def log_action(db_name, query_tuple):
    async with aiosqlite.connect(db_name) as db:
        if db_name == "history.db":
            await db.execute("INSERT INTO search_logs (user_id, type, query, date) VALUES (?, ?, ?, ?)", query_tuple)
        else:
            await db.execute("INSERT INTO payments (user_id, username, fio, date) VALUES (?, ?, ?, ?)", query_tuple)
        await db.commit()

# --- МЕНЮ ---
def main_kb(user_id):
    btns = [
        [KeyboardButton(text="👤 ФИО (DEEP SEARCH ⭐️)")],
        [KeyboardButton(text="👤 VK Profile"), KeyboardButton(text="📞 Пробив Номера")],
        [KeyboardButton(text="🌐 IP Address"), KeyboardButton(text="👤 Профиль")]
    ]
    if user_id == ADMIN_ID:
        btns.append([KeyboardButton(text="📥 Оплаты"), KeyboardButton(text="📥 Логи")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

# --- МОДУЛЬ IP (MAX SCAN) ---
async def generate_ip_report(ip):
    async with session.get(f"http://ip-api.com/json/{ip}?fields=66846719") as r:
        d = await r.json()
        if d.get('status') != 'success': return "❌ Ошибка: IP адрес не найден."
        
        report = (
            f"<b>[ 🌐 IP ANALYSIS: {d['query']} ]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>[ 📍 ГЕОЛОКАЦИЯ ]</b>\n"
            f"├ Страна: {d.get('country')} ({d.get('countryCode')})\n"
            f"├ Город: {d.get('city')}, {d.get('regionName')}\n"
            f"├ Индекс: {d.get('zip')}\n"
            f"└ Карта: <a href='https://www.google.com/maps?q={d.get('lat')},{d.get('lon')}'>ОТКРЫТЬ GOOGLE MAPS</a>\n\n"
            f"<b>[ 📡 ПРОВАЙДЕР ]</b>\n"
            f"├ ISP: {d.get('isp')}\n"
            f"├ Организация: {d.get('org')}\n"
            f"└ AS: {d.get('as')}\n\n"
            f"<b>[ 🚨 БЕЗОПАСНОСТЬ ]</b>\n"
            f"├ VPN/Proxy: {'⚠️ ДА' if d.get('proxy') else '✅ НЕТ'}\n"
            f"├ Мобильный: {'📱 ДА' if d.get('mobile') else '🏠 НЕТ'}\n"
            f"└ Хостинг: {'🖥 ДА' if d.get('hosting') else '👤 ЮЗЕР'}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )
        return report

# --- МОДУЛЬ ВК (MAX SEARCH) ---
async def generate_vk_report(target):
    fields = "photo_max,city,country,bdate,status,online,last_seen,followers_count,career,education,relation,domain"
    url = f"https://api.vk.com/method/users.get?user_ids={target}&fields={fields}&access_token={VK_TOKEN}&v=5.131"
    async with session.get(url) as r:
        data = await r.json()
        if 'response' not in data or not data['response']: return "❌ Профиль не найден."
        u = data['response'][0]
        
        rel_map = {1: "Свободен(а)", 2: "Есть друг/подруга", 3: "Помолвлен(а)", 4: "В браке", 5: "Всё сложно", 6: "В активном поиске", 7: "Влюблен(а)", 8: "В гражданском браке"}
        
        report = (
            f"<b>[ 👤 ВК ДОСЬЕ: {u.get('first_name')} {u.get('last_name')} ]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"├ ID: <code>{u.get('id')}</code>\n"
            f"├ Ник: <code>{u.get('domain', '---')}</code>\n"
            f"├ ДР: <code>{u.get('bdate', 'Скрыто')}</code>\n"
            f"├ Город: {u.get('city', {}).get('title', 'Не указан')}\n"
            f"├ Статус: <i>{u.get('status', '---')}</i>\n"
            f"├ Сем. положение: {rel_map.get(u.get('relation', 0), 'Скрыто')}\n"
            f"├ ВУЗ: {u.get('university_name', 'Скрыто')}\n"
            f"├ Подписчиков: {u.get('followers_count', 0)}\n"
            f"├ Активность: {'🟢 ONLINE' if u.get('online') else '🔴 OFFLINE'}\n"
            f"└ Ссылка: vk.com/{u.get('domain', 'id'+str(u.get('id')))}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )
        return report

# --- МОДУЛЬ НОМЕРА ---
async def generate_phone_report(phone):
    clean = "".join(filter(str.isdigit, phone))
    if clean.startswith("8"): clean = "7" + clean[1:]
    return (f"<b>[ 📂 НОМЕР: +{clean} ]</b>\n"
            f"├ <a href='https://numbuster.com/ru/phone/{clean}'>Теги (NumBuster)</a>\n"
            f"├ <a href='https://www.truecaller.com/search/ru/{clean}'>Имена (TrueCaller)</a>\n"
            f"└ <a href='https://www.google.com/search?q=site:avito.ru+%22{clean}%22'>Объявления Avito</a>")

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(m: Message):
    await m.answer("<b>SYSTEM START...</b>\nМодули OSINT (VK/IP/Phone/FIO) готовы.\n\nПодпишись: @owhig 👤", reply_markup=main_kb(m.from_user.id), parse_mode="HTML")

@dp.message(F.text == "🌐 IP Address")
async def s_ip(m: Message, state: FSMContext):
    await m.answer("🌐 <b>Введите IP адрес для анализа:</b>", parse_mode="HTML")
    await state.set_state(States.ip)

@dp.message(States.ip)
async def p_ip(m: Message, state: FSMContext):
    await log_action("history.db", (m.from_user.id, "IP", m.text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    await m.answer(await generate_ip_report(m.text), parse_mode="HTML", disable_web_page_preview=True)
    await state.clear()

@dp.message(F.text == "👤 VK Profile")
async def s_vk(m: Message, state: FSMContext):
    await m.answer("👤 <b>Введите ID или короткое имя ВК:</b>", parse_mode="HTML")
    await state.set_state(States.vk)

@dp.message(States.vk)
async def p_vk(m: Message, state: FSMContext):
    await log_action("history.db", (m.from_user.id, "VK", m.text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    await m.answer(await generate_vk_report(m.text), parse_mode="HTML", disable_web_page_preview=True)
    await state.clear()

@dp.message(F.text == "📞 Пробив Номера")
async def s_p(m: Message, state: FSMContext):
    await m.answer("📞 <b>Введите номер телефона:</b>", parse_mode="HTML")
    await state.set_state(States.phone)

@dp.message(States.phone)
async def p_p(m: Message, state: FSMContext):
    await log_action("history.db", (m.from_user.id, "PHONE", m.text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    await m.answer(await generate_phone_report(m.text), parse_mode="HTML", disable_web_page_preview=True)
    await state.clear()

@dp.message(F.text == "📥 Оплаты")
async def d_p(m: Message):
    if m.from_user.id == ADMIN_ID: await m.answer_document(FSInputFile("plat.db"))

@dp.message(F.text == "📥 Логи")
async def d_l(m: Message):
    if m.from_user.id == ADMIN_ID: await m.answer_document(FSInputFile("history.db"))

@dp.message(F.text == "👤 Профиль")
async def prof(m: Message):
    status = "Admin" if m.from_user.id == ADMIN_ID else "User"
    await m.answer(f"👤 <b>Ваш ID:</b> <code>{m.from_user.id}</code>\n<b>Статус:</b> {status}", parse_mode="HTML")

# --- СЕРВЕР И АНТИ-СОН ---
async def handle(r): return web.Response(text="SHERLOCK ACTIVE")
async def self_ping():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    while url:
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
