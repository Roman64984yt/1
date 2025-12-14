import asyncio
import time
import os
import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

# 🔥 ИМПОРТ МОЗГОВ (БЕСПЛАТНЫЙ GPT)
import g4f
from g4f.client import Client

load_dotenv()

# Проверка токена
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("Ошибка: Не найден BOT_TOKEN в переменных окружения!")
    exit()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
client = Client() # Создаем клиента для нейросети

# ─────────────────── НАСТРОЙКИ ───────────────────
ADMIN_CHAT = -1003408598270
ALLOWED_GROUP = -1003344194941
SUPER_ADMINS = {7240918914, 5982573836, 6660200937}

START_TIME = time.time()
REPORTS_COUNT = 0
# ──────────────────────────────────────────────────

taken_by = {}

# ─────────────── НЕЙРОСЕТЬ (.gpt запрос) ───────────────
@router.message(
    F.text.lower().startswith((".gpt", ".гпт")),
    F.chat.id.in_({ALLOWED_GROUP, ADMIN_CHAT}) # Работает и в группе, и в админке
)
async def ask_gpt(message: Message):
    # Разделяем текст: ".гпт Привет" -> ["ignore", "Привет"]
    args = message.text.split(maxsplit=1)
    
    # Если написали просто ".гпт" без вопроса
    if len(args) < 2:
        return await message.reply("🤖 <b>Пример:</b> <code>.гпт Как дела?</code>", parse_mode="HTML")
    
    prompt = args[1]
    
    # Показываем статус "печатает..."
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    status_msg = await message.reply("🧠 <i>Подключаюсь к нейросети...</i>", parse_mode="HTML")

    try:
        # Отправляем запрос. Используем asyncio.to_thread, чтобы бот не завис ожидая ответа
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo", # g4f сам подберет лучшую бесплатную модель
            messages=[{"role": "user", "content": prompt}],
        )
        
        gpt_text = response.choices[0].message.content
        
        # Обрезаем, если ответ слишком длинный для Телеграма
        if len(gpt_text) > 4000:
            gpt_text = gpt_text[:4000] + "...(обрезано)"

        # Отправляем ответ
        await status_msg.edit_text(f"🤖 <b>Ответ AI:</b>\n\n{gpt_text}", parse_mode="HTML")

    except Exception as e:
        print(f"Ошибка GPT: {e}")
        # g4f иногда глючит, так как он бесплатный, сообщаем об этом
        await status_msg.edit_text("⚠️ <b>Нейросеть перегружена.</b> Попробуй позже.", parse_mode="HTML")


# ─────────────── РАССЫЛКА ИНФО (.рассылка) ───────────────
@router.message(F.text == ".рассылка", F.chat.id == ADMIN_CHAT)
async def send_info_broadcast(message: Message):
    if message.from_user.id not in SUPER_ADMINS:
        return await message.reply("⛔ Только главные админы могут делать рассылку.")

    info_text = """
🛡 <b>СИСТЕМА РЕПОРТОВ АКТИВНА</b>

Уважаемые участники! Напоминаем, как пользоваться ботом модерации:

🚨 <b>Заметили нарушение?</b>
Ответьте на сообщение нарушителя командой:
<code>.ж</code> или <code>.жалоба</code>

🆘 <b>Нужно позвать админа?</b>
Напишите в чат:
<code>.админ</code>
    """
    try:
        await bot.send_message(ALLOWED_GROUP, info_text, parse_mode="HTML")
        await message.reply("✅ Информация отправлена!")
    except Exception as e:
        await message.reply(f"❌ Ошибка отправки: {e}")

# ─────────────── СТАТУС БОТА ───────────────
@router.message(F.text.lower() == "бот", F.chat.id == ADMIN_CHAT)
async def bot_status_check(message: Message):
    uptime_seconds = int(time.time() - START_TIME)
    uptime_str = str(datetime.timedelta(seconds=uptime_seconds))
    text = (
        f"🤖 <b>Системный статус:</b>\n"
        f"✅ <b>Состояние:</b> Работаю\n"
        f"⏱ <b>Аптайм:</b> {uptime_str}\n"
        f"📩 <b>Обработано жалоб:</b> {REPORTS_COUNT}"
    )
    await message.answer(text, parse_mode="HTML")


# ─────────────── ЖАЛОБА (.жалоба) ───────────────
@router.message(F.reply_to_message, F.text.startswith((".жалоба", ".ж")), F.chat.type.in_({"supergroup", "group"}))
async def handle_report(message: Message):
    if message.chat.id != ALLOWED_GROUP: return

    global REPORTS_COUNT
    REPORTS_COUNT += 1

    offender = message.reply_to_message.from_user
    reporter = message.from_user
    link = message.reply_to_message.get_url()

    if offender.id == reporter.id: return await message.answer("😂 На себя нельзя!", reply_to_message_id=message.reply_to_message.message_id)
    if offender.is_bot: return await message.answer("🤖 На ботов нельзя.", reply_to_message_id=message.reply_to_message.message_id)

    text = f"ЖАЛОБА В ГРУППЕ\nНарушитель: {offender.full_name}\nКто пожаловался: {reporter.full_name}\nСсылка: {link}\nВремя: {time.strftime('%d.%m.%Y %H:%M')}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Принять жалобу", callback_data=f"take_{message.reply_to_message.message_id}_{reporter.id}_{message.chat.id}")]])

    await bot.send_message(ADMIN_CHAT, text, reply_markup=kb, disable_web_page_preview=True)
    await message.delete()
    await message.answer("Жалоба отправлена администрации!", reply_to_message_id=message.reply_to_message.message_id)


# ─────────────── ПРИНЯТЬ ЖАЛОБУ ───────────────
@router.callback_query(F.data.startswith("take_"))
async def take_complaint(call: CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS: return await call.answer("Только главные админы.", show_alert=True)
    _, msg_id, reporter_id, chat_id = call.data.split("_")
    msg_id, reporter_id, chat_id = int(msg_id), int(reporter_id), int(chat_id)
    admin = call.from_user
    taken_by[call.message.message_id] = admin.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Закрыть жалобу ✅", callback_data=f"close_{call.message.message_id}")]])
    await bot.send_message(chat_id, f"@{admin.username or admin.full_name} взял(а) вашу жалобу.", reply_to_message_id=msg_id)
    await call.message.edit_text(call.message.text + f"\n\nВзялся: @{admin.username or admin.full_name}", reply_markup=kb)
    await call.answer("Вы взяли жалобу")


# ─────────────── ЗАКРЫТЬ ЖАЛОБУ ───────────────
@router.callback_query(F.data.startswith("close_"))
async def close_complaint(call: CallbackQuery):
    admin_chat_msg_id = int(call.data.split("_")[1])
    taker_id = taken_by.get(admin_chat_msg_id)
    if call.from_user.id != taker_id and call.from_user.id not in SUPER_ADMINS: return await call.answer("Закрыть может только взявший админ.", show_alert=True)
    await call.message.edit_text(call.message.text + f"\n\nЖалоба закрыта @{call.from_user.username or call.from_user.full_name}")
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("Жалоба закрыта")
    taken_by.pop(admin_chat_msg_id, None)


# ─────────────── ВЫЗОВ АДМИНА ───────────────
@router.message(F.text.startswith((".админ", ".admin")), F.chat.id == ALLOWED_GROUP)
async def call_admin(message: Message):
    await message.delete()
    await message.answer("Админы вызваны! Скоро ответим ⏳")
    await bot.send_message(ADMIN_CHAT, f"🚨 ВЫЗОВ АДМИНА!\nОт: {message.from_user.full_name}\nСсылка: {message.get_url()}")


# ─────────────── ПОМОЩЬ ───────────────
@router.message(F.text.startswith((".помощь", ".help")), F.chat.id == ALLOWED_GROUP)
async def send_help(message: Message):
    await message.answer("Команды:\n• Нарушение → ответ → .жалоба\n• Позвать админа → .админ\n• Вопрос ИИ → .гпт Ваш вопрос")

dp.include_router(router)

# ─────────────── WEB SERVER ───────────────
async def health_check(request): return web.Response(text="Bot is alive!")

async def start_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Веб-сервер запущен на порту {port}")

async def main():
    await start_server()
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот работает!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
