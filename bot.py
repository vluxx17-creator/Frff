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
    vk = State()

# --- БАЗЫ ДАННЫХ ---
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
        [KeyboardButton(text="📧 Email OSINT"), KeyboardButton(text="📞 Номер")],
        [KeyboardButton(text="🌐 IP Address"), KeyboardButton(text="👤 VK Profile")],
        [KeyboardButton(text="👤 Профиль")]
    ]
    if user_id == ADMIN_ID:
        btns.append([KeyboardButton(text="📥 Оплаты"), KeyboardButton(text="📥 Логи")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

# --- ГЕНЕРАТОР ОТЧЕТА (SHERLOCK STYLE) ---
async def generate_sherlock_report(fio):
    enc = urllib.parse.quote(fio)
    vk_url = f"https://api.vk.com/method/users.search?q={enc}&count=1&fields=bdate,city,country,site,domain,education,status&access_token={VK_TOKEN}&v=5.131"
    
    # Соцсети
    sources = {
        "VK": f"https://vk.com/search?c%5Bsection%5D=people&c%5Bq%5D={enc}",
        "OK": f"https://ok.ru/search?st.query={enc}",
        "FB": f"https://www.facebook.com/public/{enc.replace(' ', '-')}",
        "Insta": f"https://www.google.com/search?q=site:instagram.com+%22{enc}%22",
        "TikTok": f"https://www.tiktok.com/search/user?q={enc}",
        "LinkedIn": f"https://www.linkedin.com/search/results/people/?keywords={enc}",
        "Twitter": f"https://twitter.com/search?q={enc}&src=typed_query&f=user"
    }
    
    # Госреестры и Утечки
    gov = {
        "ФССП (Долги)": f"https://fssp.gov.ru/iss/ip?is%5Bvariant%5D=1&is%5Blast_name%5D={enc.split()[0] if len(enc.split())>0 else ''}",
        "Суды РФ": f"https://bsr.sudrf.ru/bigblue/search.html#q=%22{enc}%22",
        "Налоги/ИНН": f"https://www.google.com/search?q=site:nalog.gov.ru+%22{enc}%22",
        "Банкротство": f"https://bankrot.fedresurs.ru/Searchers/PrivatePersonSearch.aspx?name={enc}"
    }

    async with session.get(vk_url) as r:
        v_data = await r.json()
        u = v_data['response']['items'][0] if 'response' in v_data and v_data['response']['items'] else {}
        
        report = (
            f"<b>[ 📂 СФОРМИРОВАНО ДОСЬЕ: {fio.upper()} ]</b>\n"
            f"<code>Статус: Сбор данных завершен успешно</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>[ 👤 ОСНОВНАЯ ИНФОРМАЦИЯ ]</b>\n"
            f"├ ID ВК: <code>{u.get('id', 'Не найден')}</code>\n"
            f"├ Город: <code>{u.get('city', {}).get('title', 'Данные скрыты')}</code>\n"
            f"├ ДР: <code>{u.get('bdate', 'Не указано')}</code>\n"
            f"├ Статус: <i>{u.get('status', 'Нет данных')}</i>\n"
            f"└ Профиль: vk.com/{u.get('domain', 'id'+str(u.get('id','')))}\n\n"
            
            f"<b>[ 🌐 СОЦИАЛЬНЫЕ СЕТИ ]</b>\n"
            f"├ <a href='{sources['VK']}'>ВКонтакте</a> | <a href='{sources['OK']}'>OK.ru</a>\n"
            f"├ <a href='{sources['FB']}'>Facebook</a> | <a href='{sources['Insta']}'>Instagram</a>\n"
            f"└ <a href='{sources['TikTok']}'>TikTok</a> | <a href='{sources['LinkedIn']}'>LinkedIn</a>\n\n"
            
            f"<b>[ ⚖️ ГОСУДАРСТВЕННЫЕ РЕЕСТРЫ ]</b>\n"
            f"├ <a href='{gov['ФССП (Долги)']}'>Задолженности ФССП</a>\n"
            f"├ <a href='{gov['Суды РФ']}'>Судебные дела и акты</a>\n"
            f"└ <a href='{gov['Банкротство']}'>Реестр банкротов</a>\n\n"
            
            f"<b>[ 🖼 ПОИСК ПО ФОТО ]</b>\n"
            f"├ <a href='https://yandex.ru/images/search?text={enc}'>Yandex Images</a>\n"
            f"└ <a href='https://www.google.com/search?q={enc}&tbm=isch'>Google Lens</a>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <i>OSINT SHERLOCK v5.0 | @searchHams_bot</i>"
        )
        return report

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(m: Message):
    await m.answer(
        "<b>SYSTEM START...</b>\nМодуль OSINT загружен.\nДоступ к базам: ✅\n\nПодпишись: @owhig 👤",
        reply_markup=main_kb(m.from_user.id), parse_mode="HTML"
    )

@dp.message(F.text == "👤 ФИО (DEEP SEARCH ⭐️)")
async def s_fio(m: Message, state: FSMContext):
    await m.answer("📝 <b>Введите ФИО цели полностью:</b>\nНапр: <i>Иванов Иван Иванович</i>", parse_mode="HTML")
    await state.set_state(States.fio)

@dp.message(States.fio)
async def p_fio(m: Message, state: FSMContext):
    fio = m.text
    if m.from_user.id == ADMIN_ID:
        await m.answer("🔓 <b>ADMIN BYPASS:</b> Генерирую отчет...")
        await log_action("plat.db", (m.from_user.id, m.from_user.username, fio, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        await m.answer(await generate_sherlock_report(fio), parse_mode="HTML", disable_web_page_preview=True)
    else:
        pending_searches[m.from_user.id] = fio
        await m.answer_invoice(
            title="OSINT REPORT: DEEP SCAN",
            description=f"Цель: {fio}",
            prices=[LabeledPrice(label="15 Stars", amount=15)],
            payload=f"fio_{m.from_user.id}",
            currency="XTR",
            start_parameter="search"
        )
    await state.clear()

@dp.pre_checkout_query()
async def pre_c(q: PreCheckoutQuery): await q.answer(ok=True)

@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def success_p(m: Message):
    fio = pending_searches.get(m.from_user.id, "Неизвестно")
    await log_action("plat.db", (m.from_user.id, m.from_user.username, fio, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    await m.answer("💎 <b>ОПЛАТА ПОЛУЧЕНА.</b> Формирую досье...", parse_mode="HTML")
    await m.answer(await generate_sherlock_report(fio), parse_mode="HTML", disable_web_page_preview=True)

@dp.message(F.text == "📧 Email OSINT")
async def s_e(m: Message, state: FSMContext):
    await m.answer("📧 <b>Введите Email для анализа:</b>", parse_mode="HTML")
    await state.set_state(States.email)

@dp.message(States.email)
async def p_e(m: Message, state: FSMContext):
    await log_action("history.db", (m.from_user.id, "EMAIL", m.text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    report = (
        f"<b>[ 🔍 EMAIL ANALYSIS: {m.text} ]</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"├ <a href='https://epieos.com/?q={m.text}'>Аккаунты (Epieos)</a>\n"
        f"├ <a href='https://leakcheck.net/search?type=email&check={m.text}'>Проверка утечек</a>\n"
        f"└ <a href='https://intelx.io/?s={m.text}'>База IntelX</a>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    await m.answer(report, parse_mode="HTML", disable_web_page_preview=True)
    await state.clear()

@dp.message(F.text == "📞 Номер")
async def s_p(m: Message, state: FSMContext):
    await m.answer("📞 <b>Введите номер (+7...):</b>")
    await state.set_state(States.phone)

@dp.message(States.phone)
async def p_p(m: Message, state: FSMContext):
    await log_action("history.db", (m.from_user.id, "PHONE", m.text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    try:
        p = phonenumbers.parse(m.text)
        await m.answer(f"📞 <b>ИНФО:</b> {m.text}\n└ Страна: {p.country_code}\n└ <a href='https://numbuster.com/ru/phone/{m.text}'>Поиск в NumBuster</a>", parse_mode="HTML")
    except: await m.answer("❌ Ошибка формата")
    await state.clear()

@dp.message(F.text == "📥 Оплаты")
async def d_p(m: Message):
    if m.from_user.id == ADMIN_ID: await m.answer_document(FSInputFile("plat.db"))

@dp.message(F.text == "📥 Логи")
async def d_l(m: Message):
    if m.from_user.id == ADMIN_ID: await m.answer_document(FSInputFile("history.db"))

@dp.message(F.text == "👤 Профиль")
async def prof(m: Message):
    await m.answer(f"👤 <b>ID:</b> <code>{m.from_user.id}</code>\n<b>User:</b> @{m.from_user.username}", parse_mode="HTML")

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
    
    port = int(os.environ.get("PORT", 8080))
    await asyncio.gather(web.TCPSite(runner, '0.0.0.0', port).start(), dp.start_polling(bot), self_ping())

if __name__ == "__main__":
    asyncio.run(main())
