import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

# Твой токен
TOKEN = '8690934918:AAHDIGmTophZaoTIIb2e1x-TRT8nOVswZhM'

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

async def get_ip_info(ip: str):
  fields = "status,country,city,lat,lon,isp,org,zip,timezone,as"
  url = f"http://ip-api.com/json/{ip}?fields={fields}&lang=ru"
  async with aiohttp.ClientSession() as session:
    try:
      async with session.get(url) as resp:
        return await resp.json()
    except:
      return {"status": "fail"}

@dp.message(Command("start"))
async def cmd_start(message: Message):
  await message.answer("Пришли IP-адрес для получения данных.")

@dp.message()
async def ip_tracker(message: Message):
  ip = message.text.strip()
  data = await get_ip_info(ip)
  if data.get('status') == 'success':
    response = (
      f"📍 IP: {ip}\n"
      f"🌍 Регион: {data.get('country')}, {data.get('city')}\n"
      f"📮 Индекс: {data.get('zip')}\n"
      f"🏢 Провайдер: {data.get('isp')}\n"
      f"🌐 AS: {data.get('as')}\n"
      f"🕒 Пояс: {data.get('timezone')}\n"
      f"📍 Координаты: {data.get('lat')}, {data.get('lon')}\n"
      f"🔗 Карта: https://www.google.com/maps/search/?api=1&query={data.get('lat')},{data.get('lon')}"
    )
  else:
    response = "❌ Не удалось найти информацию."
  await message.answer(response)

async def main():
  await dp.start_polling(bot)

if __name__ == "__main__":
  asyncio.run(main())