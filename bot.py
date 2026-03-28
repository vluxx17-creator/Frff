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
    if user_id == ADMIN_ID: btns.append([KeyboardButton(text="📥 Оплаты"), KeyboardButton(text="📥 Логи")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

# --- МОДУЛЬ ВК (MAX SEARCH) ---
async def generate_vk_report(target):
    fields = "photo_max,city,country,bdate,status,online,last_seen,followers_count,common_count,counters,career,military,education,relation,personal,contacts,site"
    url = f"https://api.vk.com/method/users.get?user_ids={target}&fields={fields}&access_token={VK_TOKEN}&v=5.131"
    async with session.get(url) as r:
        data = await r.json()
        if 'response' not in data or not data['response']: return "❌ Профиль не найден."
        u = data['response'][0]
        
        # Обработка данных
        rel_map = {1: "Свободен(а)", 2: "Есть друг/подруга", 3: "Помолвлен(а)", 4: "В браке", 5: "Всё сложно", 6: "В активном поиске", 7: "Влюблен(а)", 8: "В гражданском браке"}
        edu = f"{u.get('university_name', '')} ({u.get('faculty_name', '')})" if u.get('university_name') else "Скрыто"
        
        report = (
            f"<b>[ 👤 ВК ДОСЬЕ: {u.get('first_name')} {u.get('last_name')} ]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>[ 🆔 ИДЕНТИФИКАЦИЯ ]</b>\n"
            f"├ ID: <code>{u.get('id')}</code>\n"
            f"├ Ник: <code>{u.get('domain', '---')}</code>\n"
            f"├ Ссылка: vk.com/{u.get('domain', 'id'+str(u.get('id')))}\n\n"
            f"<b>[ 👤 ЛИЧНЫЕ ДАННЫЕ ]</b>\n"
            f"├ ДР: <code>{u.get('bdate', 'Скрыто')}</code>\n"
            f"├ Статус: <i>{u.get('status', '---')}</i>\n"
            f"├ Семейное положение: {rel_map.get(u.get('relation', 0), 'Скрыто')}\n"
            f"├ Город: {u.get('city', {}).get('title', 'Не указан')}\n\n"
            f"<b>[ 🎓 КАРЬЕРА И УЧЕБА ]</b>\n"
            f"├ ВУЗ: {edu}\n"
            f"└ Карьера: {u.get('career', [{}])[0].get('company', 'Скрыто') if u.get('career') else 'Нет данных'}\n\n"
            f"<b>[ 📊 СТАТИСТИКА ]</b>\n"
            f"├ Подписчиков: {u.get('followers_count', 0)}\n"
            f"├ Активность: {'🟢 ONLINE' if u.get('online') else '🔴 OFFLINE'}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )
        return report, u.get('photo_max')

# --- МОДУЛЬ IP (MAX SEARCH) ---
async def generate_ip_report(ip):
    async with session.get(f"http://ip-api.com/json/{ip}?fields=66846719") as r:
        d = await r.json()
        if d.get('status') != 'success': return "❌ Ошибка: IP не существует."
        
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

# --- МОДУЛЬ TON (MAX SEARCH) ---
async def generate_ton_report(addr):
    async with session.get(f"https://tonapi.io/v2/accounts/{addr}") as r:
        if r.status != 200: return "❌ Ошибка доступа к блокчейну."
        d = await r.json()
        balance = d.get('balance', 0) / 10**9
        report = (
            f"<b>[ 💎 TON WALLET AUDIT ]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"├ Адрес: <code>{addr[:8]}...{addr[-8:]}</code>\n"
            f"├ Баланс: <b>{balance:.4f} TON</b>\n"
            f"├ Статус: {d.get('status', 'Unknown')}\n"
            f"├ Версия: {d.get('interfaces', ['Unknown'])[0]}\n"
            f"└ DNS домены: {', '.join(d.get('dns_names', ['Нет']))}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 <a href='https://tonviewer.com/{addr}'>Смотреть транзакции в TonViewer</a>"
        )
        return report

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(m: Message):
    await m.answer("<b>SYSTEM START...</b>\nМодули OSINT ULTIMATE загружены.\n\nПодпишись: @owhig 👤", reply_markup=main_kb(m.from_user.id), parse_mode="HTML")

@dp.message(F.text == "👤 ВК Профиль")
async def s_v(m: Message, state: FSMContext):
    await m.answer("👤 <b>Введите ID или Ссылку ВК:</b>", parse_mode="HTML")
    await state.set_state(States.vk)

@dp.message(States.vk)
async def p_v(m: Message, state: FSMContext):
    await log_to_db("history.db", (m.from_user.id, "VK", m.text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    report, photo = await generate_vk_report(m.text)
    if photo: await m.answer_photo(photo, caption=report, parse_mode="HTML")
    else: await m.answer(report, parse_mode="HTML")
    await state.clear()

@dp.message(F.text == "🌐 IP Address")
async def s_i(m: Message, state: FSMContext):
    await m.answer("🌐 <b>Введите IP адрес:</b>", parse_mode="HTML")
    await state.set_state(States.ip)

@dp.message(States.ip)
async def p_i(m: Message, state: FSMContext):
    await log_to_db("history.db", (m.from_user.id, "IP", m.text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    await m.answer(await generate_ip_report(m.text), parse_mode="HTML", disable_web_page_preview=True)
    await state.clear()

@dp.message(F.text == "💎 TON Wallet")
async def s_t(m: Message, state: FSMContext):
    await m.answer("💎 <b>Введите TON адрес:</b>", parse_mode="HTML")
    await state.set_state(States.ton)

@dp.message(States.ton)
async def p_t(m: Message, state: FSMContext):
    await log_to_db("history.db", (m.from_user.id, "TON", m.text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    await m.answer(await generate_ton_report(m.text), parse_mode="HTML", disable_web_page_preview=True)
    await state.clear()

@dp.message(F.text == "📥 Оплаты")
async def d_p(m: Message):
    if m.from_user.id == ADMIN_ID: await m.answer_document(FSInputFile("plat.db"))

@dp.message(F.text == "📥 Логи")
async def d_l(m: Message):
    if m.from_user.id == ADMIN_ID: await m.answer_document(FSInputFile("history.db"))

@dp.message(F.text == "👤 Профиль")
async def prof(m: Message):
    await m.answer(f"👤 <b>ID:</b> <code>{m.from_user.id}</code>\n<b>Status:</b> {'Admin' if m.from_user.id == ADMIN_ID else 'User'}", parse_mode="HTML")

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
