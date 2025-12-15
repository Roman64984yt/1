import asyncio
import time
import os
import datetime
import random
import html
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiohttp import web

# --- НОВЫЕ ИМПОРТЫ ДЛЯ БАЗЫ ДАННЫХ ---
from supabase import create_client, Client

load_dotenv()

# Проверка токена
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("Ошибка: Не найден BOT_TOKEN!")
    # Временная заглушка, чтобы код не падал, если ты забыл .env, но лучше используй .env
    # BOT_TOKEN = "ТВОЙ_ТОКЕН_ЗДЕСЬ" 
    if not BOT_TOKEN: exit()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# ─────────────────── НАСТРОЙКИ SUPABASE ───────────────────
SUPABASE_URL = "https://tvriklnmvrqstgnyxhry.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR2cmlrbG5tdnJxc3Rnbnl4aHJ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU4MjcyNTAsImV4cCI6MjA4MTQwMzI1MH0.101vOltGd1N30c4whqs8nY6K0nuE9LsMFqYCKCANFRQ"

# Инициализация клиента базы данных
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Подключение к Supabase успешно инициализировано.")
except Exception as e:
    print(f"❌ Ошибка подключения к Supabase: {e}")

# Функция добавления/обновления пользователя
def upsert_user(tg_id, username, full_name):
    try:
        data = {
            "user_id": tg_id,          # БЫЛО: telegram_id -> СТАЛО: user_id
            "username": username or "No Nickname",
            "full_name": full_name     # Добавили сохранение полного имени
        }
        # on_conflict теперь тоже "user_id"
        supabase.table("users").upsert(data, on_conflict="user_id").execute()
    except Exception as e:
        print(f"⚠️ Ошибка записи в БД: {e}")

# ─────────────────── НАСТРОЙКИ БОТА ───────────────────
ADMIN_CHAT = -1003408598270      
ALLOWED_GROUP = -1003344194941   

# 👑 ВЛАДЕЛЕЦ
OWNER_ID = 7240918914  

# 🛡 АДМИНЫ
SUPER_ADMINS = {7240918914, 5982573836, 6660200937}

START_TIME = time.time()
REPORTS_COUNT = 0

# 📦 ОПЕРАТИВНАЯ ПАМЯТЬ
pending_requests = set()
active_support = set()
taken_by = {}  
# ──────────────────────────────────────────────────

# ─────────────── 1. ГЛАВНОЕ МЕНЮ (/start) ───────────────
@router.message(Command("start"), F.chat.type == "private")
async def send_welcome(message: Message):
    user = message.from_user
    
    # ПЕРЕДАЕМ ТЕПЕРЬ И ИМЯ (user.full_name)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, upsert_user, user.id, user.username, user.full_name)
    
    # --------------------------------
    
    # html.escape защищает от ников типа "<Name>"
    safe_name = html.escape(user.full_name)
    
    text = (
        f"👋 Привет, {safe_name}!\n\n"
        "Это бот для доступа в закрытый чат.\n"
        "Вы внесены в базу данных пользователей.\n\n"
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

    await call.message.edit_text(
        "✅ <b>Заявка отправлена!</b>\n\n"
        "Администратор рассмотрит её в ближайшее время.\n"
        "Вам придет уведомление.\n"
        "Заявки принимаются с 14:00 МСК (простите я один, в такое время я сплю)",
        parse_mode="HTML"
    )

    # ЗАЩИТА ИМЕН ОТ ОШИБОК
    safe_name = html.escape(call.from_user.full_name)
    username = f"@{call.from_user.username}" if call.from_user.username else "нет ника"
    
    text_admin = (
        f"🛎 <b>НОВАЯ ЗАЯВКА НА ВХОД</b>\n\n"
        f"👤 <b>Кто:</b> {safe_name} ({username})\n"
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
    
    safe_admin_name = html.escape(call.from_user.full_name)

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
            await call.message.edit_text(f"{call.message.text}\n\n✅ ОДОБРЕНО ({safe_admin_name})", reply_markup=None)
        except Exception as e:
            await call.answer(f"Ошибка создания ссылки: {e}", show_alert=True)

    elif action == "no":
        try:
            kb_sup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Написать в поддержку", callback_data="req_support")]])
            await bot.send_message(user_id, "⛔ Ваша заявка отклонена.", parse_mode="HTML", reply_markup=kb_sup)
        except: pass
        
        await call.message.edit_text(f"{call.message.text}\n\n❌ ОТКЛОНЕНО ({safe_admin_name})", reply_markup=None)
    
    await call.answer()


# ─────────────── 3. ЧАТ ПОДДЕРЖКИ ───────────────
@router.callback_query(F.data == "req_support")
async def request_support_handler(call: CallbackQuery):
    user_id = call.from_user.id
    
    if user_id in active_support:
        return await call.answer("У вас уже открыт чат с админом. Пишите сообщения.", show_alert=True)

    safe_name = html.escape(call.from_user.full_name)

    text_admin = (
        f"🆘 <b>ЗАПРОС В ПОДДЕРЖКУ</b>\n\n"
        f"👤 <b>От:</b> {safe_name}\n"
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
    safe_admin_name = html.escape(call.from_user.full_name)

    try:
        await bot.send_message(user_id, "👨‍💻 <b>Администратор подключился!</b>\nТеперь вы можете писать сюда сообщения, я передам их админу.", parse_mode="HTML")
    except:
        return await call.answer("Не могу написать юзеру (блок?)", show_alert=True)

    kb_end = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⛔ Завершить чат", callback_data=f"chat_end_{user_id}")]])
    
    await call.message.edit_text(
        f"{call.message.text}\n\n✅ <b>ЧАТ АКТИВЕН</b>\nАдмин: {safe_admin_name}\n\n<i>Чтобы ответить юзеру, сделайте REPLY (Ответить) на его сообщения, которые придут ниже.</i>",
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
        await bot.send_message(user_id, "✅ Диалог завершен администратором.\nЕсли нужно, подайте заявку заново через /start")
    except: pass

    await call.message.edit_text(f"{call.message.text}\n\n🏁 <b>Чат завершен.</b>", reply_markup=None, parse_mode="HTML")
    await call.answer("Диалог закрыт")


# ─────────────── 4. ПЕРЕСЫЛКА СООБЩЕНИЙ (МОСТ) ───────────────
@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def user_message_handler(message: Message):
    user_id = message.from_user.id
    
    if user_id in active_support:
        safe_name = html.escape(message.from_user.full_name)
        safe_text = html.escape(message.text) if message.text else "[Файл/Медиа]"

        text_to_admin = (
            f"📩 <b>Сообщение от юзера</b>\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Имя: {safe_name}\n\n"
            f"{safe_text}"
        )
        await bot.send_message(ADMIN_CHAT, text_to_admin, parse_mode="HTML")
        return

    if user_id not in pending_requests:
        await message.answer("Используйте меню: /start")


@router.message(F.chat.id == ADMIN_CHAT, F.reply_to_message)
async def admin_reply_handler(message: Message):
    replied_text = message.reply_to_message.text or message.reply_to_message.caption or ""
    
    if "📩 Сообщение от юзера" in replied_text and "ID:" in replied_text:
        try:
            user_id_line = [line for line in replied_text.split('\n') if "ID:" in line][0]
            target_user_id = int(user_id_line.split(":")[1].strip().replace("<code>", "").replace("</code>", ""))

            safe_reply_text = html.escape(message.text) if message.text else "[Файл]"
            
            await bot.send_message(target_user_id, f"👨‍💻 <b>Админ:</b>\n{safe_reply_text}", parse_mode="HTML")
            await message.reply("✅ Отправлено")
        except Exception as e:
            await message.reply(f"❌ Не удалось отправить.\nОшибка: {e}")


# ─────────────── 5. ЖАЛОБЫ И МОДЕРАЦИЯ ───────────────
@router.message(
    F.reply_to_message,
    F.text.startswith((".жалоба", ".ж")),
    F.chat.type.in_({"supergroup", "group"})
)
async def handle_report(message: Message):
    if message.chat.id != ALLOWED_GROUP:
        return

    global REPORTS_COUNT
    REPORTS_COUNT += 1

    offender = message.reply_to_message.from_user
    reporter = message.from_user
    link = message.reply_to_message.get_url()

    if offender.id == reporter.id:
        return await message.reply(f"😂 {reporter.mention_html()}, на себя жаловаться нельзя!", parse_mode="HTML")
    if offender.is_bot:
        return await message.reply(f"🤖 {reporter.mention_html()}, на ботов жаловаться нельзя.", parse_mode="HTML")

    # Безопасное сообщение
    content = message.reply_to_message.text or message.reply_to_message.caption or '[Вложение/Медиа]'
    safe_content = html.escape(content)

    text = f"""
<b>ЖАЛОБА В ГРУППЕ</b>

👮‍♂️ <b>Нарушитель:</b> {offender.mention_html()}
👤 <b>Кто пожаловался:</b> {reporter.mention_html()}

📄 <b>Сообщение:</b>
{safe_content}

🔗 <b>Ссылка:</b> {link}
⏰ <b>Время:</b> {time.strftime('%d.%m.%Y %H:%M')}
    """.strip()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Принять жалобу",
            callback_data=f"take_{message.reply_to_message.message_id}_{reporter.id}_{message.chat.id}"
        )
    ]])

    await bot.send_message(ADMIN_CHAT, text, reply_markup=kb, disable_web_page_preview=True, parse_mode="HTML")
    await message.delete()
    
    await message.answer(f"{reporter.mention_html()}, жалоба отправлена администрации!", parse_mode="HTML")


@router.callback_query(F.data.startswith("take_"))
async def take_complaint(call: CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS:
        return await call.answer("У вас нет прав модератора.", show_alert=True)

    msg_id = int(call.data.split("_")[1])
    chat_id = int(call.data.split("_")[3])
    admin = call.from_user

    taken_by[msg_id] = admin.id

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Закрыть жалобу ✅", callback_data=f"close_{msg_id}")
    ]])

    try:
        await bot.send_message(chat_id, f"👮‍♂️ Администратор @{admin.username or admin.full_name} принял вашу жалобу.", reply_to_message_id=msg_id)
    except: pass

    await call.message.edit_text(
        f"{call.message.text}\n\n✅ <b>Взялся:</b> @{admin.username or admin.full_name}",
        reply_markup=kb,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await call.answer("Вы взяли жалобу")


@router.callback_query(F.data.startswith("close_"))
async def close_complaint(call: CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS:
        return await call.answer("У вас нет прав.", show_alert=True)

    await call.message.edit_text(
        f"{call.message.text}\n\n🔒 <b>Жалоба закрыта</b> администратором @{call.from_user.username or call.from_user.full_name}",
        reply_markup=None,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await call.answer("Жалоба закрыта")


# ─────────────── 6. ОСТАЛЬНОЕ (.рассылка, .инфо) ───────────────
@router.message(F.text == ".рассылка", F.chat.id == ADMIN_CHAT)
async def send_info_broadcast(message: Message):
    if message.from_user.id not in SUPER_ADMINS: return
    
    info_text = """
🛡 <b>СИСТЕМА УПРАВЛЕНИЯ ЧАТОМ</b>

Уважаемые участники! Напоминаем функционал бота:

🚨 <b>Модерация:</b>
Заметили нарушение? Ответьте командой:
<code>.ж</code> или <code>.жалоба</code>

🆘 <b>Связь с админами:</b>
Напишите в чат:
<code>.админ</code>

🔐 <b>Как пригласить друга?</b>
Наш чат закрытый. Чтобы попасть сюда:
1. Перешлите друга в ЛС к этому боту.
2. Пусть он нажмет <code>/start</code> и подаст заявку.
3. После одобрения бот выдаст ему персональную ссылку.

🔮 <b>Развлечения:</b>
Шар судьбы (Да/Нет):
<code>.инфо Ваш вопрос</code>

Приятного общения! 🫡
    """
    await bot.send_message(ALLOWED_GROUP, info_text, parse_mode="HTML")
    await message.reply("✅")


@router.message(F.text.lower().startswith(".инфо"), F.chat.id.in_({ALLOWED_GROUP, ADMIN_CHAT}))
async def magic_ball(message: Message):
    answers = ["✅ Да", "❌ Нет", "⚠️ Рискованно", "🤔 50/50", "👀 Попробуй"]
    await message.reply(f"🔮 {random.choice(answers)}")


@router.message(F.text.lower() == "бот", F.chat.id == ADMIN_CHAT)
async def bot_status(message: Message):
    uptime = str(datetime.timedelta(seconds=int(time.time() - START_TIME)))
    await message.answer(f"🤖 OK\nUp: {uptime}\nЗаявок: {len(pending_requests)}\nЧатов: {len(active_support)}")


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

