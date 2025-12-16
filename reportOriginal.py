import asyncio
import time
import os
import datetime
import random
import html
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatMemberUpdated
from aiogram.filters import Command, ChatMemberUpdatedFilter, KICKED, LEFT, RESTRICTED, MEMBER, ADMINISTRATOR, CREATOR
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

# --- ИМПОРТЫ ДЛЯ БАЗЫ ДАННЫХ ---
from supabase import create_client, Client

load_dotenv()

# --- КОНФИГ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Если запускаешь локально, вставь токен ниже:
# BOT_TOKEN = "ТВОЙ_ТОКЕН_ТУТ"

ADMIN_CHAT = -1003408598270      
ALLOWED_GROUP = -1003344194941   
OWNER_ID = 7240918914  
SUPER_ADMINS = {7240918914, 5982573836, 6660200937}

SUPABASE_URL = "https://tvriklnmvrqstgnyxhry.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR2cmlrbG5tdnJxc3Rnbnl4aHJ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU4MjcyNTAsImV4cCI6MjA4MTQwMzI1MH0.101vOltGd1N30c4whqs8nY6K0nuE9LsMFqYCKCANFRQ"

# --- ИНИЦИАЛИЗАЦИЯ ---
if not BOT_TOKEN:
    print("Ошибка: Не найден BOT_TOKEN!")
    exit()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Подключение к Supabase успешно.")
except Exception as e:
    print(f"❌ Ошибка подключения к Supabase: {e}")

# --- ПАМЯТЬ БОТА ---
pending_requests = set()
active_support = set()
taken_by = {}
user_invites = {}  # 🆕 ТУТ ХРАНИМ ССЫЛКИ: {user_id: "https://t.me/..."}
START_TIME = time.time()

# --- ФУНКЦИИ БД ---
def upsert_user(tg_id, username, full_name):
    try:
        data = {
            "user_id": tg_id,
            "username": username or "No Nickname",
            "full_name": full_name
        }
        supabase.table("users").upsert(data, on_conflict="user_id").execute()
    except Exception as e:
        print(f"⚠️ Ошибка записи в БД: {e}")

def get_user_bans(user_id):
    try:
        response = supabase.table("users").select("ban_global, ban_requests, ban_support, ban_reason").eq("user_id", user_id).execute()
        if response.data:
            return response.data[0]
    except Exception as e:
        print(f"Ошибка чтения банов: {e}")
    return None

# ─────────────────── ЛОГИКА БОТА ───────────────────

# 1. СТАРТ
@router.message(Command("start"), F.chat.type == "private")
async def send_welcome(message: Message):
    user = message.from_user
    loop = asyncio.get_event_loop()
    
    await loop.run_in_executor(None, upsert_user, user.id, user.username, user.full_name)
    bans = await loop.run_in_executor(None, get_user_bans, user.id)
    
    if bans and bans.get("ban_global") is True:
        reason = bans.get("ban_reason") or "Нарушение правил"
        await message.answer(f"⛔ <b>ВЫ ЗАБЛОКИРОВАНЫ.</b>\n\nПричина: {html.escape(reason)}", parse_mode="HTML")
        return

    safe_name = html.escape(user.full_name)
    text = (
        f"👋 Привет, {safe_name}!\n\n"
        "Это бот для доступа в закрытый чат <b>Quick Talk | Chat</b>.\n"
        "Вы внесены в базу данных.\n\n"
        "Выберите действие ниже:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛡 Пройти проверку (Вход)", callback_data="req_join")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="req_support")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# 2. ЗАЯВКИ
@router.callback_query(F.data == "req_join")
async def join_request_handler(call: CallbackQuery):
    user_id = call.from_user.id
    loop = asyncio.get_event_loop()
    bans = await loop.run_in_executor(None, get_user_bans, user_id)
    
    if bans and (bans.get("ban_global") is True or bans.get("ban_requests") is True):
        await call.answer("⛔ Вам запрещено подавать заявки!", show_alert=True)
        return

    if user_id in pending_requests:
        return await call.answer("⏳ Ваша заявка уже на рассмотрении.", show_alert=True)

    pending_requests.add(user_id)

    await call.message.edit_text(
        "✅ <b>Заявка отправлена!</b>\n\nАдминистратор рассмотрит её в ближайшее время.",
        parse_mode="HTML"
    )

    safe_name = html.escape(call.from_user.full_name)
    username = f"@{call.from_user.username}" if call.from_user.username else "нет ника"
    
    text_admin = (
        f"🛎 <b>НОВАЯ ЗАЯВКА</b>\n"
        f"👤 {safe_name} ({username})\n"
        f"🆔 <code>{user_id}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Пустить", callback_data=f"invite_yes_{user_id}"),
        InlineKeyboardButton(text="❌ Отказ", callback_data=f"invite_no_{user_id}")
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
            # Создаем ссылку
            invite = await bot.create_chat_invite_link(
                chat_id=ALLOWED_GROUP,
                name=f"User {user_id}",
                member_limit=1,
                expire_date=datetime.timedelta(hours=24)
            )
            
            # 🆕 СОХРАНЯЕМ ССЫЛКУ В ПАМЯТЬ
            user_invites[user_id] = invite.invite_link

            await bot.send_message(
                user_id,
                f"🎉 <b>Добро пожаловать!</b>\n\nВот ваша ссылка (одноразовая):\n{invite.invite_link}",
                parse_mode="HTML"
            )
            await call.message.edit_text(f"{call.message.text}\n\n✅ ОДОБРЕНО", reply_markup=None)
        except Exception as e:
            await call.answer(f"Ошибка: {e}", show_alert=True)

    elif action == "no":
        try:
            await bot.send_message(user_id, "⛔ Ваша заявка отклонена.")
        except: pass
        await call.message.edit_text(f"{call.message.text}\n\n❌ ОТКЛОНЕНО", reply_markup=None)
    
    await call.answer()

# 🆕 3. АВТО-УДАЛЕНИЕ ССЫЛКИ ПРИ ВХОДЕ
@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def on_user_join(event: ChatMemberUpdated):
    user_id = event.from_user.id
    chat_id = event.chat.id
    
    # Проверяем, есть ли у этого юзера активная ссылка
    if user_id in user_invites:
        invite_link = user_invites[user_id]
        try:
            # Сжигаем ссылку
            await bot.revoke_chat_invite_link(chat_id=chat_id, invite_link=invite_link)
            print(f"🔥 Ссылка для {user_id} была сожжена после входа.")
        except Exception as e:
            print(f"⚠️ Не удалось сжечь ссылку: {e}")
        
        # Удаляем из памяти
        del user_invites[user_id]

# 4. ПОДДЕРЖКА
@router.callback_query(F.data == "req_support")
async def request_support_handler(call: CallbackQuery):
    user_id = call.from_user.id
    loop = asyncio.get_event_loop()
    bans = await loop.run_in_executor(None, get_user_bans, user_id)
    
    if bans and (bans.get("ban_global") is True or bans.get("ban_support") is True):
        await call.answer("⛔ Бан поддержки!", show_alert=True)
        return

    if user_id in active_support:
        return await call.answer("Чат уже открыт.", show_alert=True)

    safe_name = html.escape(call.from_user.full_name)
    text_admin = f"🆘 <b>ПОДДЕРЖКА</b>\n👤 {safe_name}\n🆔 <code>{user_id}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Начать чат", callback_data=f"chat_start_{user_id}")]])
    
    await bot.send_message(ADMIN_CHAT, text_admin, reply_markup=kb, parse_mode="HTML")
    await call.message.edit_text("⏳ Ждите ответа администратора.", parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("chat_start_"))
async def start_support_chat(call: CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS: return await call.answer("Только админы.", show_alert=True)
    user_id = int(call.data.split("_")[2])
    active_support.add(user_id)
    await bot.send_message(user_id, "👨‍💻 Админ на связи! Пишите.")
    kb_end = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⛔ Завершить", callback_data=f"chat_end_{user_id}")]])
    await call.message.edit_text(f"{call.message.text}\n\n✅ ЧАТ АКТИВЕН", reply_markup=kb_end, parse_mode="HTML")

@router.callback_query(F.data.startswith("chat_end_"))
async def end_support_chat(call: CallbackQuery):
    user_id = int(call.data.split("_")[2])
    if user_id in active_support: active_support.remove(user_id)
    try: await bot.send_message(user_id, "✅ Диалог завершен.")
    except: pass
    await call.message.edit_text("🏁 Чат завершен.", reply_markup=None)

# 5. ПЕРЕСЫЛКА И АДМИНКА
@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def user_message_handler(message: Message):
    user_id = message.from_user.id
    if user_id in active_support:
        await bot.send_message(ADMIN_CHAT, f"📩 <b>{html.escape(message.from_user.full_name)}</b> (ID: {user_id}):\n{message.text or '[Файл]'}", parse_mode="HTML")
    elif user_id not in pending_requests:
        await message.answer("Используйте меню: /start")

@router.message(F.chat.id == ADMIN_CHAT, F.reply_to_message)
async def admin_reply_handler(message: Message):
    replied = message.reply_to_message.text or ""
    if "ID:" in replied:
        try:
            target_id = int(replied.split("ID:")[1].split(")")[0].strip()) if "ID:" in replied else int(replied.split("ID: ")[1].split("\n")[0])
            await bot.send_message(target_id, f"👨‍💻 <b>Админ:</b>\n{message.text}", parse_mode="HTML")
            await message.reply("✅")
        except: pass

# 6. ЖАЛОБЫ (.ж)
@router.message(F.reply_to_message, F.text.startswith((".жалоба", ".ж")), F.chat.id == ALLOWED_GROUP)
async def handle_report(message: Message):
    offender = message.reply_to_message.from_user
    text = f"👮‍♂️ <b>ЖАЛОБА</b>\nНа: {offender.mention_html()}\nОт: {message.from_user.mention_html()}\n🔗 {message.reply_to_message.get_url()}"
    await bot.send_message(ADMIN_CHAT, text, parse_mode="HTML")
    await message.delete()
    await message.answer("Жалоба отправлена.")

# --- ЗАПУСК ---
dp.include_router(router)
async def health_check(request): return web.Response(text="Alive")
async def start_server():
    app = web.Application(); app.router.add_get('/', health_check)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", 8080))).start()

async def main():
    await start_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
