import asyncio
import time
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web  # Добавлен импорт для веб-сервера

load_dotenv()

# Если токена нет в переменных, бот упадет с понятной ошибкой
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("Ошибка: Не найден BOT_TOKEN в переменных окружения!")
    exit()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# ─────────────────── НАСТРОЙКИ ───────────────────
ADMIN_CHAT = -1003408598270
ALLOWED_GROUP = -1003344194941
SUPER_ADMINS = {7240918914, 5982573836, 6660200937}
# ──────────────────────────────────────────────────

taken_by = {}


# ─────────────── ЖАЛОБА (.жалоба или .ж) ───────────────
@router.message(
    F.reply_to_message,
    F.text.startswith((".жалоба", ".ж")),
    F.chat.type.in_({"supergroup", "group"})
)
async def handle_report(message: Message):
    if message.chat.id != ALLOWED_GROUP:
        return

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
        InlineKeyboardButton(
            text="Принять жалобу",
            callback_data=f"take_{message.reply_to_message.message_id}_{reporter.id}_{message.chat.id}"
        )
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

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Закрыть жалобу ✅",
            callback_data=f"close_{call.message.message_id}"
        )
    ]])

    await bot.send_message(chat_id,
                           f"@{admin.username or admin.full_name} взял(а) вашу жалобу, ожидайте решения.",
                           reply_to_message_id=msg_id)

    await call.message.edit_text(call.message.text + f"\n\nВзялся: @{admin.username or admin.full_name}",
                                 reply_markup=kb)
    await call.answer("Вы взяли жалобу")


# ─────────────── ЗАКРЫТЬ ЖАЛОБУ ───────────────
@router.callback_query(F.data.startswith("close_"))
async def close_complaint(call: CallbackQuery):
    admin_chat_msg_id = int(call.data.split("_")[1])
    taker_id = taken_by.get(admin_chat_msg_id)

    if call.from_user.id != taker_id and call.from_user.id not in SUPER_ADMINS:
        return await call.answer("Закрыть может только тот, кто взял, или главный админ.", show_alert=True)

    await call.message.edit_text(
        call.message.text + f"\n\nЖалоба закрыта @{call.from_user.username or call.from_user.full_name}")
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("Жалоба закрыта")
    taken_by.pop(admin_chat_msg_id, None)


# ─────────────── ВЫЗОВ АДМИНА (ФИКС) ───────────────
@router.message(
    F.text.startswith((".админ", ".admin")),
    F.chat.id == ALLOWED_GROUP
)
async def call_admin(message: Message):
    await message.delete()
    await message.answer("Админы вызваны! Скоро ответим ⏳")

    # Уведомление в админ-чат
    await bot.send_message(
        ADMIN_CHAT,
        f"🚨 ВЫЗОВ АДМИНА!\n"
        f"От: {message.from_user.full_name} (@{message.from_user.username or 'нет'})\n"
        f"Время: {time.strftime('%d.%m.%Y %H:%M')}\n"
        f"Сообщение: {message.text}\n"
        f"Ссылка: {message.get_url()}"
    )


# ─────────────── ПОМОЩЬ ───────────────
@router.message(F.text.startswith((".помощь", ".help")), F.chat.id == ALLOWED_GROUP)
async def send_help(message: Message):
    help_text = """
КАК ЭТО РАБОТАЕТ (2 секунды):

• Нарушение → отвечаете → пишете .жалоба (или коротко .ж)
• Просто позвать админа → пишете .админ

Всё. Больше ничего знать не надо.
Спасибо, что помогаете держать чат чистым ❤️
    """
    await message.answer(help_text)


dp.include_router(router)


# ─────────────── WEB SERVER ДЛЯ RENDER/KEEP-ALIVE ───────────────
async def health_check(request):
    return web.Response(text="Bot is alive!")


async def start_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render обычно предоставляет порт в переменной окружения, или используем 8080
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Веб-сервер для пинга запущен на порту {port}")


async def main():
    print("Бот запускается...")
    # Запускаем сервер для пинга
    await start_server()

    # Сбрасываем вебхуки и запускаем бота
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот работает: .жалоба | .ж | .админ | .помощь")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())