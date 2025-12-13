import asyncio
import time
import os
import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("Ошибка: Не найден BOT_TOKEN!")
    exit()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# ─────────────────── НАСТРОЙКИ ───────────────────
ADMIN_CHAT = -1003408598270
ALLOWED_GROUP = -1003344194941
SUPER_ADMINS = {7240918914, 5982573836, 6660200937}

START_TIME = time.time()
REPORTS_COUNT = 0

# 🔥 БАЗА ДАННЫХ В ОПЕРАТИВНОЙ ПАМЯТИ
USER_CACHE = {} 
# ──────────────────────────────────────────────────

taken_by = {}

# ─────────────── СЛЕЖКА (ЗАПОМИНАЕМ ЮЗЕРОВ) ───────────────
@router.message(F.chat.id == ALLOWED_GROUP)
async def observer_handler(message: Message):
    if message.from_user and message.from_user.username:
        USER_CACHE[message.from_user.username.lower()] = message.from_user.id

# ─────────────── МУТ ИЗ АДМИНКИ (С AI-ОТВЕТОМ) ───────────────
@router.message(
    F.text.lower().startswith(".мут"),
    F.chat.id == ADMIN_CHAT
)
async def remote_mute_command(message: Message):
    if message.from_user.id not in SUPER_ADMINS:
        return await message.reply("⛔ ACCESS DENIED.")

    args = message.text.split()
    target_id = None
    target_name = "Unknown"
    duration = 1 

    # Логика поиска (по реплаю или нику)
    if message.reply_to_message:
        if message.reply_to_message.forward_from:
            target_id = message.reply_to_message.forward_from.id
            target_name = message.reply_to_message.forward_from.full_name
        else:
            target_id = message.reply_to_message.from_user.id
            target_name = message.reply_to_message.from_user.full_name
    else:
        for arg in args:
            if arg.startswith("@"):
                username = arg[1:].lower()
                target_id = USER_CACHE.get(username)
                target_name = arg
                break
    
    for arg in args:
        if arg.isdigit():
            duration = int(arg)
            break

    if duration > 1:
        duration = 1

    if not target_id:
        return await message.reply("⚠️ TARGET_NOT_FOUND: Юзер не найден в кэше памяти.")

    lines = message.text.split('\n')
    reason = lines[1] if len(lines) > 1 else "Нарушение протоколов общения"

    until = int(time.time()) + (duration * 60)
    permissions = types.ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False
    )

    try:
        # 1. Мутим пользователя
        await bot.restrict_chat_member(ALLOWED_GROUP, target_id, permissions, until_date=until)

        # 2. 🔥 БОТ ПИШЕТ В ОБЩИЙ ЧАТ (ПУГАЮЩЕЕ СООБЩЕНИЕ)
        ai_message = (
            f"🛡 <b>NEURAL PROTECTION SYSTEM</b>\n\n"
            f"👤 <b>Объект:</b> {target_name}\n"
            f"📉 <b>Статус:</b> Ограничение доступа\n"
            f"⏱ <b>Таймер:</b> {duration} мин.\n\n"
            f"🤖 <b>Анализ нейросети:</b>\n"
            f"Обнаружена аномальная активность. Искусственный интеллект оценил вероятность нарушения как 99.9%.\n\n"
            f"📜 <b>Вердикт:</b> <i>{reason}</i>"
        )
        await bot.send_message(ALLOWED_GROUP, ai_message, parse_mode="HTML")

        # 3. Отчет админу
        await message.reply(f"✅ EXECUTION COMPLETE.\nЦель {target_name} нейтрализована.")

    except Exception as e:
        await message.reply(f"⚠️ SYSTEM FAILURE: {e}")


# ─────────────── ОСТАЛЬНЫЕ ФУНКЦИИ (БЕЗ ИЗМЕНЕНИЙ) ───────────────

@router.message(F.text == ".рассылка", F.chat.id == ADMIN_CHAT)
async def send_info_broadcast(message: Message):
    if message.from_user.id not in SUPER_ADMINS: return
    info_text = """
🛡 <b>СИСТЕМА РЕПОРТОВ АКТИВНА</b>
🚨 <b>Нарушение?</b> Ответьте: <code>.ж</code>
🆘 <b>Админ?</b> Напишите: <code>.админ</code>
    """
    await bot.send_message(ALLOWED_GROUP, info_text, parse_mode="HTML")
    await message.reply("✅ Отправлено")

@router.message(F.text.lower().startswith((".всем", ".say")), F.chat.id == ADMIN_CHAT)
async def broadcast_message(message: Message):
    if message.from_user.id not in SUPER_ADMINS: return
    try:
        await bot.send_message(ALLOWED_GROUP, message.text.split(maxsplit=1)[1])
        await message.reply("✅ Отправлено")
    except: await message.reply("❌ Ошибка")

@router.message(F.text.lower() == "бот", F.chat.id == ADMIN_CHAT)
async def bot_status_check(message: Message):
    uptime = str(datetime.timedelta(seconds=int(time.time() - START_TIME)))
    await message.answer(f"🤖 <b>Status:</b> OK\n⏱ <b>Uptime:</b> {uptime}\n💾 <b>Cache:</b> {len(USER_CACHE)} users", parse_mode="HTML")

@router.message(F.reply_to_message, F.text.startswith((".жалоба", ".ж")), F.chat.type.in_({"supergroup", "group"}))
async def handle_report(message: Message):
    if message.chat.id != ALLOWED_GROUP: return
    if message.from_user.username: USER_CACHE[message.from_user.username.lower()] = message.from_user.id
    global REPORTS_COUNT; REPORTS_COUNT += 1
    
    text = f"ЖАЛОБА\nНа: {message.reply_to_message.from_user.full_name}\nОт: {message.from_user.full_name}\nСсылка: {message.reply_to_message.get_url()}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Принять", callback_data=f"take_{message.reply_to_message.message_id}_{message.from_user.id}_{message.chat.id}")]])
    await bot.send_message(ADMIN_CHAT, text, reply_markup=kb)
    await message.delete()
    await message.answer("Жалоба отправлена!", reply_to_message_id=message.reply_to_message.message_id)

@router.callback_query(F.data.startswith("take_"))
async def take_complaint(call: CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS: return await call.answer("Нет прав")
    admin = call.from_user; taken_by[call.message.message_id] = admin.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Закрыть ✅", callback_data=f"close_{call.message.message_id}")]])
    chat_id = int(call.data.split("_")[3]); msg_id = int(call.data.split("_")[1])
    await bot.send_message(chat_id, f"@{admin.username} взял жалобу.", reply_to_message_id=msg_id)
    await call.message.edit_text(call.message.text + f"\n\nВзялся: @{admin.username}", reply_markup=kb)

@router.callback_query(F.data.startswith("close_"))
async def close_complaint(call: CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS: return await call.answer("Нет прав")
    await call.message.edit_text(call.message.text + f"\n\nЗакрыто: @{call.from_user.username}")

@router.message(F.text.startswith((".админ", ".admin")), F.chat.id == ALLOWED_GROUP)
async def call_admin(message: Message):
    await message.delete(); await message.answer("Админы вызваны!")
    await bot.send_message(ADMIN_CHAT, f"🚨 ВЫЗОВ!\nОт: {message.from_user.full_name}\n{message.get_url()}")

@router.message(F.text.startswith((".помощь", ".help")), F.chat.id == ALLOWED_GROUP)
async def send_help(message: Message):
    await message.answer(".жалоба - репорт\n.админ - вызов")

dp.include_router(router)

async def health_check(request): return web.Response(text="Bot is alive!")
async def start_server():
    app = web.Application(); app.router.add_get('/', health_check)
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.getenv("PORT", 8080))
    await web.TCPSite(runner, '0.0.0.0', port).start()

async def main():
    await start_server(); await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
