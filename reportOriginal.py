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
# Бот будет запоминать: "username" -> user_id
USER_CACHE = {} 
# ──────────────────────────────────────────────────

taken_by = {}

# ─────────────── СЛЕЖКА (ЗАПОМИНАЕМ ЮЗЕРОВ) ───────────────
# Этот хендлер работает молча и просто записывает всех, кто пишет в чат
@router.message(F.chat.id == ALLOWED_GROUP)
async def observer_handler(message: Message):
    if message.from_user and message.from_user.username:
        # Записываем юзера в кэш (в нижнем регистре для поиска)
        USER_CACHE[message.from_user.username.lower()] = message.from_user.id
        # Если нужно, можно вывести в консоль для отладки
        # print(f"Запомнил: {message.from_user.username} -> {message.from_user.id}")


# ─────────────── МУТ ПО @USERNAME ИЛИ РЕПЛАЮ ───────────────
# Работает из АДМИНКИ. Можно писать: .мут @ник 1
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
    duration = 1  # По умолчанию 1 минута

    # ВАРИАНТ 1: Мут реплаем (если переслали сообщение нарушителя в админку)
    if message.reply_to_message:
        # Если это пересланное сообщение, берем ID оригинала
        if message.reply_to_message.forward_from:
            target_id = message.reply_to_message.forward_from.id
            target_name = message.reply_to_message.forward_from.full_name
        else:
            # Если просто ответили на сообщение в админке
            target_id = message.reply_to_message.from_user.id
            target_name = message.reply_to_message.from_user.full_name

    # ВАРИАНТ 2: Мут по нику (.мут @username 1)
    else:
        for arg in args:
            if arg.startswith("@"):
                username = arg[1:].lower() # Убираем @ и переводим в нижний регистр
                target_id = USER_CACHE.get(username)
                target_name = arg
                break
    
    # Ищем время в команде
    for arg in args:
        if arg.isdigit():
            duration = int(arg)
            break

    # Ограничение до 1 минуты (для прикола)
    if duration > 1:
        duration = 1

    # Если ID не найден
    if not target_id:
        return await message.reply(
            "⚠️ <b>ERROR: TARGET_NOT_FOUND</b>\n\n"
            "Бот не знает этого пользователя.\n"
            "1. Либо он еще ничего не писал в чат (после перезагрузки бота).\n"
            "2. Либо вы ошиблись в нике.",
            parse_mode="HTML"
        )

    # Причина (все строки, кроме первой)
    lines = message.text.split('\n')
    reason = lines[1] if len(lines) > 1 else "Violation of protocols"

    # Выполняем мут
    until = int(time.time()) + (duration * 60)
    permissions = types.ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False
    )

    try:
        # Важно: мутим в ALLOWED_GROUP, а не в админке
        await bot.restrict_chat_member(ALLOWED_GROUP, target_id, permissions, until_date=until)

        log_text = (
            f"⚙️ <b>SYSTEM EXECUTION:</b>\n"
            f"target: <code>{target_name}</code> (ID: {target_id})\n"
            f"command: <code>remote_mute</code>\n"
            f"duration: <code>{duration} min</code>\n"
            f"reason: <i>{reason}</i>\n\n"
            f"✅ <b>Операция выполнена успешно.</b>"
        )
        await message.reply(log_text, parse_mode="HTML")

    except Exception as e:
        await message.reply(f"⚠️ SYSTEM FAILURE: {e}")


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

Администрация видит все жалобы и реагирует максимально быстро.
Спасибо, что помогаете поддерживать порядок в чате! 🫡
    """
    try:
        await bot.send_message(ALLOWED_GROUP, info_text, parse_mode="HTML")
        await message.reply("✅ Информация о работе бота отправлена в общий чат!")
    except Exception as e:
        await message.reply(f"❌ Ошибка отправки: {e}")


# ─────────────── РУПОР (.всем текст) ───────────────
@router.message(F.text.lower().startswith((".всем", ".say")), F.chat.id == ADMIN_CHAT)
async def broadcast_message(message: Message):
    if message.from_user.id not in SUPER_ADMINS:
        return await message.reply("⛔ Нет прав.")
    command_args = message.text.split(maxsplit=1)
    if len(command_args) < 2:
        return await message.reply("📢 Пример: .всем Привет всем!")
    text_to_send = command_args[1]
    try:
        await bot.send_message(ALLOWED_GROUP, text_to_send)
        await message.reply("✅ Сообщение отправлено!")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


# ─────────────── СТАТУС БОТА ───────────────
@router.message(F.text.lower() == "бот", F.chat.id == ADMIN_CHAT)
async def bot_status_check(message: Message):
    uptime_seconds = int(time.time() - START_TIME)
    uptime_str = str(datetime.timedelta(seconds=uptime_seconds))
    text = (
        f"🤖 <b>Системный статус:</b>\n"
        f"✅ <b>Состояние:</b> Работаю\n"
        f"⏱ <b>Аптайм:</b> {uptime_str}\n"
        f"📩 <b>Обработано жалоб:</b> {REPORTS_COUNT}\n"
        f"💾 <b>Людей в кэше:</b> {len(USER_CACHE)}"
    )
    await message.answer(text, parse_mode="HTML")


# ─────────────── ЖАЛОБА (.жалоба) ───────────────
@router.message(F.reply_to_message, F.text.startswith((".жалоба", ".ж")), F.chat.type.in_({"supergroup", "group"}))
async def handle_report(message: Message):
    if message.chat.id != ALLOWED_GROUP:
        return
    
    # Тоже запоминаем кто пишет жалобу
    if message.from_user.username:
        USER_CACHE[message.from_user.username.lower()] = message.from_user.id

    global REPORTS_COUNT
    REPORTS_COUNT += 1
    offender = message.reply_to_message.from_user
    reporter = message.from_user
    link = message.reply_to_message.get_url()
    if offender.id == reporter.id:
        return await message.answer("😂 На себя нельзя!", reply_to_message_id=message.reply_to_message.message_id)
    if offender.is_bot:
        return await message.answer("🤖 На ботов нельзя.", reply_to_message_id=message.reply_to_message.message_id)
    text = f"""
ЖАЛОБА В ГРУППЕ
Нарушитель: {offender.full_name} (@{offender.username or 'нет'})
Кто пожаловался: {reporter.full_name} (@{reporter.username or 'нет'})
Сообщение:
{message.reply_to_message.text or message.reply_to_message.caption or '[медиа]'}
Ссылка: {link}
Время: {time.strftime('%d.%m.%Y %H:%M')}
    """.strip()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Принять жалобу", callback_data=f"take_{message.reply_to_message.message_id}_{reporter.id}_{message.chat.id}")
    ]])
    await bot.send_message(ADMIN_CHAT, text, reply_markup=kb, disable_web_page_preview=True)
    await message.delete()
    await message.answer("Жалоба отправлена администрации!", reply_to_message_id=message.reply_to_message.message_id)


# ─────────────── ПРИНЯТЬ ЖАЛОБУ ───────────────
@router.callback_query(F.data.startswith("take_"))
async def take_complaint(call: CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS:
        return await call.answer("Только главные админы могут брать жалобы.", show_alert=True)
    _, msg_id, reporter_id, chat_id = call.data.split("_")
    msg_id, reporter_id, chat_id = int(msg_id), int(reporter_id), int(chat_id)
    admin = call.from_user
    taken_by[call.message.message_id] = admin.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Закрыть жалобу ✅", callback_data=f"close_{call.message.message_id}")]])
    await bot.send_message(chat_id, f"@{admin.username or admin.full_name} взял(а) вашу жалобу, ожидайте решения.", reply_to_message_id=msg_id)
    await call.message.edit_text(call.message.text + f"\n\nВзялся: @{admin.username or admin.full_name}", reply_markup=kb)
    await call.answer("Вы взяли жалобу")


# ─────────────── ЗАКРЫТЬ ЖАЛОБУ ───────────────
@router.callback_query(F.data.startswith("close_"))
async def close_complaint(call: CallbackQuery):
    admin_chat_msg_id = int(call.data.split("_")[1])
    taker_id = taken_by.get(admin_chat_msg_id)
    if call.from_user.id != taker_id and call.from_user.id not in SUPER_ADMINS:
        return await call.answer("Закрыть может только тот, кто взял, или главный админ.", show_alert=True)
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
    help_text = "Команды:\n• Нарушение → ответ → .жалоба\n• Позвать админа → .админ"
    await message.answer(help_text)

dp.include_router(router)

# ─────────────── WEB SERVER ───────────────
async def health_check(request):
    return web.Response(text="Bot is alive!")

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
