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
    print("Ошибка: Не найден BOT_TOKEN!")
    exit()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# ─────────────────── НАСТРОЙКИ ───────────────────
ADMIN_CHAT = -1003408598270      
ALLOWED_GROUP = -1003344194941   

# 👑 ВЛАДЕЛЕЦ (Для одобрения заявок)
OWNER_ID = 7240918914  

# 🛡 АДМИНЫ (Для репортов и поддержки)
SUPER_ADMINS = {7240918914, 5982573836, 6660200937}

START_TIME = time.time()
REPORTS_COUNT = 0

# 📦 БАЗА ДАННЫХ (В ПАМЯТИ)
pending_requests = set()
active_support = set()
# ──────────────────────────────────────────────────

# ─────────────── 1. ГЛАВНОЕ МЕНЮ (/start) ───────────────
@router.message(F.command("start"), F.chat.type == "private")
async def send_welcome(message: Message):
    text = (
        f"👋 Привет, {message.from_user.full_name}!\n\n"
        "Это бот для доступа в закрытый чат.\n"
        "Выберите действие ниже:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Подать заявку на вход", callback_data="req_join")],
        [InlineKeyboardButton(text="🆘 Поддержка (Связь с админом)", callback_data="req_support")]
    ])
    await message.answer(text, reply_markup=kb)


# ─────────────── 2. ЛОГИКА ЗАЯВОК (JOIN) ───────────────

@router.callback_query(F.data == "req_join")
async def join_request_handler(call: CallbackQuery):
    user_id = call.from_user.id
    
    if user_id in pending_requests:
        return await call.answer("⏳ Ваша заявка уже на рассмотрении. Ждите!", show_alert=True)

    pending_requests.add(user_id)

    # Ответ юзеру
    await call.message.edit_text(
        "✅ <b>Заявка отправлена!</b>\n\n"
        "Администратор рассмотрит её в ближайшее время.\n"
        "Вам придет уведомление.",
        parse_mode="HTML"
    )

    # Пишем Владельцу
    username = f"@{call.from_user.username}" if call.from_user.username else "нет ника"
    text_admin = (
        f"🛎 <b>НОВАЯ ЗАЯВКА НА ВХОД</b>\n\n"
        f"👤 <b>Кто:</b> {call.from_user.full_name} ({username})\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"⚠️ <i>Решение принимает Владелец.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Пустить (24ч)", callback_data=f"invite_yes_{user_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"invite_no_{user_id}")
    ]])
    await bot.send_message(ADMIN_CHAT, text_admin, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("invite_"))
async def process_invite_decision(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return await call.answer("⛔ Только Владелец может пускать людей!", show_alert=True)

    action = call.data.split("_")[1]
    user_id = int(call.data.split("_")[2])

    if user_id in pending_requests:
        pending_requests.remove(user_id)

    if action == "yes":
        try:
            invite = await bot.create_chat_invite_link(
                chat_id=ALLOWED_GROUP,
                name=f"User {user_id}",
                member_limit=1,
                expire_date=datetime.timedelta(hours=24)
            )
            await bot.send_message(
                user_id,
                f"🎉 <b>Добро пожаловать!</b>\n\nВаша заявка одобрена.\nВот ссылка (действует 24 часа):\n{invite.invite_link}",
                parse_mode="HTML"
            )
            await call.message.edit_text(f"{call.message.text}\n\n✅ <b>ОДОБРЕНО</b> ({call.from_user.full_name})", reply_markup=None)
        except Exception as e:
            await call.answer(f"Ошибка создания ссылки: {e}", show_alert=True)

    elif action == "no":
        try:
            kb_sup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Написать в поддержку", callback_data="req_support")]])
            await bot.send_message(user_id, "⛔ <b>Ваша заявка отклонена.</b>", parse_mode="HTML", reply_markup=kb_sup)
        except: pass
        
        await call.message.edit_text(f"{call.message.text}\n\n❌ <b>ОТКЛОНЕНО</b> ({call.from_user.full_name})", reply_markup=None)
    
    await call.answer()


# ─────────────── 3. ЧАТ ПОДДЕРЖКИ ───────────────

@router.callback_query(F.data == "req_support")
async def request_support_handler(call: CallbackQuery):
    user_id = call.from_user.id
    
    if user_id in active_support:
        return await call.answer("У вас уже открыт чат с админом. Пишите сообщения.", show_alert=True)

    text_admin = (
        f"🆘 <b>ЗАПРОС В ПОДДЕРЖКУ</b>\n\n"
        f"👤 <b>От:</b> {call.from_user.full_name}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Начать чат", callback_data=f"chat_start_{user_id}")
    ]])
    await bot.send_message(ADMIN_CHAT, text_admin, reply_markup=kb, parse_mode="HTML")
    
    await call.message.edit_text("⏳ <b>Запрос отправлен.</b>\nОжидайте, когда администратор подключится к чату.", parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("chat_start_"))
async def start_support_chat(call: CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS:
        return await call.answer("Только админы.", show_alert=True)

    user_id = int(call.data.split("_")[2])
    active_support.add(user_id)

    try:
        await bot.send_message(user_id, "👨‍💻 <b>Администратор подключился!</b>\nТеперь вы можете писать сюда сообщения, я передам их админу.", parse_mode="HTML")
    except:
        return await call.answer("Не могу написать юзеру (блок?)", show_alert=True)

    kb_end = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⛔ Завершить чат", callback_data=f"chat_end_{user_id}")]])
    
    await call.message.edit_text(
        f"{call.message.text}\n\n✅ <b>ЧАТ АКТИВЕН</b>\nАдмин: {call.from_user.full_name}\n\n<i>Чтобы ответить юзеру, сделайте REPLY (Ответить) на его сообщения, которые придут ниже.</i>",
        reply_markup=kb_end,
        parse_mode="HTML"
    )
    await call.answer("Чат начат!")


@router.callback_query(F.data.startswith("chat_end_"))
async def end_support_chat(call: CallbackQuery):
    user_id = int(call.data.split("_")[2])
    if user_id in active_support:
        active_support.remove(user_id)

    try:
        await bot.send_message(user_id, "✅ <b>Диалог завершен администратором.</b>\nЕсли нужно, подайте заявку заново через /start")
    except: pass

    await call.message.edit_text(f"{call.message.text}\n\n🏁 <b>Чат завершен.</b>", reply_markup=None, parse_mode="HTML")
    await call.answer("Диалог закрыт")


# ─────────────── 4. ПЕРЕСЫЛКА СООБЩЕНИЙ (МОСТ) ───────────────

# ДОБАВЛЕН ФИЛЬТР ~F.text.startswith("/"), ЧТОБЫ НЕ ЛОВИТЬ КОМАНДЫ
@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def user_message_handler(message: Message):
    user_id = message.from_user.id
    
    # Если чат поддержки активен
    if user_id in active_support:
        text_to_admin = (
            f"📩 <b>Сообщение от юзера</b>\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Имя: {message.from_user.full_name}\n\n"
            f"{message.text or '[Файл/Медиа]'}"
        )
        await bot.send_message(ADMIN_CHAT, text_to_admin, parse_mode="HTML")
        return

    # Если не в поддержке и не жмет кнопки
    if user_id not in pending_requests:
        await message.answer("Используйте меню: /start")


@router.message(F.chat.id == ADMIN_CHAT, F.reply_to_message)
async def admin_reply_handler(message: Message):
    replied_text = message.reply_to_message.text or message.reply_to_message.caption or ""
    
    if "📩 Сообщение от юзера" in replied_text and "ID:" in replied_text:
        try:
            user_id_line = [line for line in replied_text.split('\n') if "ID:" in line][0]
            target_user_id = int(user_id_line.split(":")[1].strip().replace("<code>", "").replace("</code>", ""))

            await bot.send_message(target_user_id, f"👨‍💻 <b>Админ:</b>\n{message.text}", parse_mode="HTML")
            await message.reply("✅ Отправлено")
        except Exception as e:
            await message.reply(f"❌ Не удалось отправить.\nОшибка: {e}")


# ─────────────── 5. ОСТАЛЬНОЙ ФУНКЦИОНАЛ ───────────────

@router.message(F.text.lower().startswith(".инфо"), F.chat.id.in_({ALLOWED_GROUP, ADMIN_CHAT}))
async def magic_ball(message: Message):
    answers = ["✅ Да", "❌ Нет", "⚠️ Рискованно", "🤔 50/50", "👀 Попробуй"]
    await message.reply(f"🔮 {random.choice(answers)}")

@router.message(F.text == ".рассылка", F.chat.id == ADMIN_CHAT)
async def send_info_broadcast(message: Message):
    if message.from_user.id not in SUPER_ADMINS: return
    await bot.send_message(ALLOWED_GROUP, "🛡 <b>ИНФО</b>\n.ж - жалоба\n.админ - вызов\n.инфо - шар", parse_mode="HTML")
    await message.reply("✅")

@router.message(F.text.lower() == "бот", F.chat.id == ADMIN_CHAT)
async def bot_status(message: Message):
    await message.answer(f"🤖 OK\nЗаявок в ожидании: {len(pending_requests)}\nЧатов поддержки: {len(active_support)}")

# Жалобы
@router.message(F.reply_to_message, F.text.startswith((".жалоба", ".ж")), F.chat.type.in_({"supergroup", "group"}))
async def handle_report(message: Message):
    if message.chat.id != ALLOWED_GROUP: return
    text = f"ЖАЛОБА\nНа: {message.reply_to_message.from_user.full_name}\nСсылка: {message.reply_to_message.get_url()}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Принять", callback_data=f"take_{message.reply_to_message.message_id}_{message.from_user.id}_{message.chat.id}")]])
    await bot.send_message(ADMIN_CHAT, text, reply_markup=kb)
    await message.answer("Жалоба отправлена!")

@router.callback_query(F.data.startswith("take_"))
async def take_complaint(call: CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS: return await call.answer("Нет прав", show_alert=True)
    await call.message.edit_text(f"{call.message.text}\n\nВзялся: {call.from_user.full_name}", reply_markup=None)

@router.message(F.text.startswith((".админ", ".admin")), F.chat.id == ALLOWED_GROUP)
async def call_admin(message: Message):
    await message.answer("Админы вызваны!")
    await bot.send_message(ADMIN_CHAT, f"🚨 ВЫЗОВ!\n{message.get_url()}")

# ─────────────── СЕРВЕР ───────────────
dp.include_router(router)
async def health_check(request): return web.Response(text="Bot is alive!")
async def start_server():
    app = web.Application(); app.router.add_get('/', health_check)
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.getenv("PORT", 8080)); await web.TCPSite(runner, '0.0.0.0', port).start()

async def main():
    await start_server(); await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
