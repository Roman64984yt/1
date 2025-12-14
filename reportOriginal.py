import asyncio
import time
import os
import datetime
import random
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

load_dotenv()

# Проверка токена
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("Ошибка: Не найден BOT_TOKEN в переменных окружения!")
    exit()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# ─────────────────── НАСТРОЙКИ ───────────────────
# ID чатов
ADMIN_CHAT = -1003408598270      
ALLOWED_GROUP = -1003344194941   

# 👑 ВЛАДЕЛЕЦ (ТОЛЬКО ОН МОЖЕТ ПУСКАТЬ ЛЮДЕЙ ПО ЗАЯВКАМ)
OWNER_ID = 7240918914  # <--- ВСТАВЬ СЮДА СВОЙ ID

# 🛡 МОДЕРАТОРЫ (Могут обрабатывать жалобы .ж)
# Владельца тоже сюда добавь, чтобы он мог и жалобы закрывать
SUPER_ADMINS = {7240918914, 5982573836, 6660200937}

START_TIME = time.time()
REPORTS_COUNT = 0
# ──────────────────────────────────────────────────

taken_by = {}

# ─────────────── 1. ОБРАБОТКА ЛС (ЗАПРОС НА ВХОД) ───────────────
@router.message(F.chat.type == "private")
async def handle_private_request(message: Message):
    user_name = message.from_user.full_name
    user_id = message.from_user.id
    username_link = f"@{message.from_user.username}" if message.from_user.username else "нет никнейма"

    # Ответ пользователю
    await message.answer(
        "👋 <b>Заявка принята!</b>\n\n"
        "Я передал ваш запрос Владельцу.\n"
        "Если он одобрит, я пришлю вам одноразовую ссылку для входа.",
        parse_mode="HTML"
    )

    # Запрос в админ-чат
    text_admin = (
        f"🛎 <b>НОВАЯ ЗАЯВКА НА ВХОД</b>\n\n"
        f"👤 <b>Кто:</b> {user_name} ({username_link})\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"💬 <b>Текст:</b> {message.text or 'Без текста'}\n\n"
        f"⚠️ <i>Решение может принять только Владелец.</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Пустить (24ч)", callback_data=f"invite_yes_{user_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"invite_no_{user_id}")
    ]])

    await bot.send_message(ADMIN_CHAT, text_admin, reply_markup=kb, parse_mode="HTML")


# ─────────────── 2. РЕШЕНИЕ (ТОЛЬКО ВЛАДЕЛЕЦ) ───────────────
@router.callback_query(F.data.startswith("invite_"))
async def process_invite_decision(call: CallbackQuery):
    # 🔥 ГЛАВНАЯ ПРОВЕРКА: Если нажал НЕ владелец
    if call.from_user.id != OWNER_ID:
        return await call.answer("⛔ Только Владелец (Full Access) может одобрять заявки!", show_alert=True)

    action = call.data.split("_")[1] # yes / no
    user_id = int(call.data.split("_")[2])

    if action == "yes":
        try:
            # Создаем ссылку
            invite = await bot.create_chat_invite_link(
                chat_id=ALLOWED_GROUP,
                name=f"Для {user_id}", 
                member_limit=1,
                expire_date=datetime.timedelta(hours=24)
            )

            await bot.send_message(
                user_id,
                f"✅ <b>Заявка одобрена Владельцем!</b>\n\nВот ваша ссылка:\n{invite.invite_link}\n\n"
                f"⚠️ <i>Ссылка действует 24 часа и только на один вход.</i>",
                parse_mode="HTML"
            )

            await call.message.edit_text(
                f"{call.message.text}\n\n✅ <b>ОДОБРЕНО</b> Владельцем ({call.from_user.full_name}).",
                reply_markup=None
            )
            await call.answer("Доступ выдан!")

        except Exception as e:
            await call.answer(f"Ошибка: {e}", show_alert=True)

    elif action == "no":
        try:
            await bot.send_message(user_id, "⛔ <b>Ваша заявка отклонена Владельцем.</b>", parse_mode="HTML")
        except:
            pass

        await call.message.edit_text(
            f"{call.message.text}\n\n❌ <b>ОТКЛОНЕНО</b> Владельцем ({call.from_user.full_name}).",
            reply_markup=None
        )
        await call.answer("Отказано.")


# ─────────────── 3. ШАР СУДЬБЫ (.инфо) ───────────────
@router.message(F.text.lower().startswith(".инфо"), F.chat.id.in_({ALLOWED_GROUP, ADMIN_CHAT}))
async def magic_ball(message: Message):
    answers = [
        "✅ <b>System:</b> Данные подтверждают — Да.",
        "✅ <b>Verdict:</b> Однозначно да.",
        "✅ <b>Analysis:</b> Вероятность успеха 99.9%.",
        "✅ <b>Log:</b> Звезды (и код) говорят — дерзай.",
        "✅ <b>Status:</b> Перспективы отличные.",
        "✅ <b>Result:</b> Утвердительный ответ.",
        
        "❌ <b>System:</b> Критическая ошибка — Нет.",
        "❌ <b>Verdict:</b> Категорически нет.",
        "❌ <b>Analysis:</b> Мои протоколы запрещают это.",
        "❌ <b>Log:</b> Даже не думай.",
        "❌ <b>Status:</b> Вероятность успеха 0%.",
        "❌ <b>Result:</b> Отрицательный результат.",
        
        "🤔 <b>System:</b> Данных недостаточно.",
        "🤔 <b>Verdict:</b> Спроси позже, сервер перегружен.",
        "🤔 <b>Analysis:</b> Вероятность 50/50.",
        "🤔 <b>Log:</b> Ответ скрыт в тумане войны.",
        "🤔 <b>Status:</b> Лучше тебе не знать сейчас.",
        
        "⚠️ <b>Warning:</b> Рискованно, но возможно.",
        "⚠️ <b>Alert:</b> Зависит от твоей удачи.",
        "⚙️ <b>Processing:</b> Сконцентрируйся и спроси снова.",
        "👀 <b>AI Vision:</b> Всё будет так, как ты захочешь.",
        "🚫 <b>Block:</b> Система не рекомендует."
    ]
    await message.reply(f"🔮 <b>Запрос обработан:</b>\n{random.choice(answers)}", parse_mode="HTML")


# ─────────────── 4. РАССЫЛКА ИНФО (.рассылка) ───────────────
@router.message(F.text == ".рассылка", F.chat.id == ADMIN_CHAT)
async def send_info_broadcast(message: Message):
    if message.from_user.id not in SUPER_ADMINS: return
    text = """
🛡 <b>СИСТЕМА РЕПОРТОВ АКТИВНА</b>

Уважаемые участники! Напоминаем команды бота:

🚨 <b>Заметили нарушение?</b>
Ответьте на сообщение нарушителя командой:
<code>.ж</code> или <code>.жалоба</code>

🆘 <b>Нужно позвать админа?</b>
Напишите в чат:
<code>.админ</code>

🔮 <b>Шар судьбы (ответ Да/Нет):</b>
Напишите: <code>.инфо Ваш вопрос</code>

Администрация видит все жалобы и реагирует максимально быстро.
Спасибо, что помогаете поддерживать порядок в чате! 🫡
    """   

# ─────────────── 5. СТАТУС БОТА ───────────────
@router.message(F.text.lower() == "бот", F.chat.id == ADMIN_CHAT)
async def bot_status_check(message: Message):
    uptime = str(datetime.timedelta(seconds=int(time.time() - START_TIME)))
    await message.answer(f"🤖 <b>Status:</b> OK\n⏱ <b>Uptime:</b> {uptime}\n📩 <b>Reports:</b> {REPORTS_COUNT}", parse_mode="HTML")


# ─────────────── 6. ЖАЛОБЫ (.ж) ───────────────
# Жалобы могут обрабатывать ВСЕ админы из списка SUPER_ADMINS
@router.message(F.reply_to_message, F.text.startswith((".жалоба", ".ж")), F.chat.type.in_({"supergroup", "group"}))
async def handle_report(message: Message):
    if message.chat.id != ALLOWED_GROUP: return
    global REPORTS_COUNT; REPORTS_COUNT += 1
    
    offender = message.reply_to_message.from_user
    reporter = message.from_user
    link = message.reply_to_message.get_url()

    if offender.id == reporter.id: return await message.answer("😂 На себя нельзя!")
    if offender.is_bot: return await message.answer("🤖 На ботов нельзя.")

    text = f"ЖАЛОБА В ГРУППЕ\nНарушитель: {offender.full_name}\nОт: {reporter.full_name}\nСсылка: {link}\nВремя: {time.strftime('%d.%m %H:%M')}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Принять жалобу", callback_data=f"take_{message.reply_to_message.message_id}_{reporter.id}_{message.chat.id}")]])

    await bot.send_message(ADMIN_CHAT, text, reply_markup=kb)
    await message.delete(); await message.answer("Жалоба отправлена!", reply_to_message_id=message.reply_to_message.message_id)

@router.callback_query(F.data.startswith("take_"))
async def take_complaint(call: CallbackQuery):
    # Тут проверяем обычный список админов
    if call.from_user.id not in SUPER_ADMINS: return await call.answer("Нет прав модератора.", show_alert=True)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Закрыть ✅", callback_data=f"close_{call.message.message_id}")]])
    chat_id = int(call.data.split("_")[3]); msg_id = int(call.data.split("_")[1])
    await bot.send_message(chat_id, f"@{call.from_user.username} взял жалобу.", reply_to_message_id=msg_id)
    await call.message.edit_text(call.message.text + f"\n\nВзялся: @{call.from_user.username}", reply_markup=kb)

@router.callback_query(F.data.startswith("close_"))
async def close_complaint(call: CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS: return await call.answer("Нет прав.", show_alert=True)
    await call.message.edit_text(call.message.text + f"\n\nЗакрыто: @{call.from_user.username}")

# ─────────────── 7. ПРОЧЕЕ ───────────────
@router.message(F.text.startswith((".админ", ".admin")), F.chat.id == ALLOWED_GROUP)
async def call_admin(message: Message):
    await message.delete(); await message.answer("Админы вызваны! ⏳")
    await bot.send_message(ADMIN_CHAT, f"🚨 ВЫЗОВ!\nОт: {message.from_user.full_name}\nСсылка: {message.get_url()}")

@router.message(F.text.startswith((".помощь", ".help")), F.chat.id == ALLOWED_GROUP)
async def send_help(message: Message): await message.answer("Команды:\n.ж - репорт\n.админ - вызов\n.инфо - шар судьбы")

dp.include_router(router)

# ─────────────── 8. WEB SERVER ───────────────
async def health_check(request): return web.Response(text="Bot is alive!")
async def start_server():
    app = web.Application(); app.router.add_get('/', health_check)
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.getenv("PORT", 8080)); await web.TCPSite(runner, '0.0.0.0', port).start()

async def main():
    await start_server(); await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
