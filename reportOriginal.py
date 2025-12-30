import asyncio
import time
import os
import datetime
import random
import html
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, 
    ChatMemberUpdated, ReplyKeyboardMarkup, KeyboardButton, ChatJoinRequest, ReplyKeyboardRemove
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, MEMBER
from aiohttp import web
from supabase import create_client, Client

load_dotenv()

# ─────────────────── КОНФИГУРАЦИЯ ───────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = "1206"  # 🔐 ТВОЙ ПАРОЛЬ ОТ АДМИНКИ
CREATOR_ID = 7240918914  # ТВОЙ ID

# Настройки чатов
ADMIN_CHAT = -1003408598270      
ALLOWED_GROUP = -1003344194941   

# Настройки Supabase
SUPABASE_URL = "https://tvriklnmvrqstgnyxhry.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR2cmlrbG5tdnJxc3Rnbnl4aHJ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU4MjcyNTAsImV4cCI6MjA4MTQwMzI1MH0.101vOltGd1N30c4whqs8nY6K0nuE9LsMFqYCKCANFRQ"

if not BOT_TOKEN: exit("NO TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ База подключена.")
except: print("❌ Ошибка БД")

START_TIME = time.time()
active_support = set()
appealing_users = set()

class AdminAuth(StatesGroup):
    waiting_for_password = State()

# ─────────────────── ФУНКЦИИ ───────────────────

def get_user_role(user_id):
    if user_id == CREATOR_ID: return 'owner'
    try:
        res = supabase.table("bot_admins").select("role").eq("user_id", user_id).execute()
        if res.data: return res.data[0]['role']
    except: pass
    return 'user'

def log_action(admin_id, action, target_id=None, details=''):
    try:
        supabase.table("admin_logs").insert({
            "admin_id": admin_id, "action": action, 
            "target_id": target_id, "details": details
        }).execute()
    except: pass

def upsert_user(tg_id, username, full_name):
    try:
        data = {"user_id": tg_id, "username": username or "No Nickname", "full_name": full_name}
        supabase.table("users").upsert(data, on_conflict="user_id").execute()
    except: pass

def get_user_bans(user_id):
    try:
        response = supabase.table("users").select("ban_global, ban_requests, ban_support, ban_reason").eq("user_id", user_id).execute()
        if response.data: return response.data[0]
    except: return None

# ─────────────────── 1. МЕНЮ И ВХОД ───────────────────

@router.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    asyncio.create_task(asyncio.to_thread(upsert_user, user.id, user.username, user.full_name))
    
    bans = await asyncio.to_thread(get_user_bans, user.id)
    if bans and bans.get("ban_global") is True:
        reason = bans.get("ban_reason") or "Нарушение правил"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📝 Подать апелляцию", callback_data="make_appeal")]])
        return await message.answer(f"⛔ <b>ВЫ ЗАБЛОКИРОВАНЫ.</b>\nПричина: {html.escape(reason)}", reply_markup=kb, parse_mode="HTML")

    safe_name = html.escape(user.full_name)
    text = (
        f"👋 Привет, {safe_name}!\n\n"
        "Это бот для доступа в <b>Quick Talk Chat</b>.\n"
        "Выберите действие ниже:"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 Админ-панель", callback_data="auth_admin")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="req_support")]
    ])
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "auth_admin")
async def auth_start(call: CallbackQuery, state: FSMContext):
    role = await asyncio.to_thread(get_user_role, call.from_user.id)
    if role == 'user': return await call.answer("⛔ Вы не админ!", show_alert=True)

    await call.message.delete()
    await call.message.answer("🔑 <b>Введите пароль:</b>", parse_mode="HTML")
    await state.set_state(AdminAuth.waiting_for_password)

@router.message(AdminAuth.waiting_for_password)
async def auth_check(message: Message, state: FSMContext):
    if message.text.strip() != ADMIN_PASSWORD:
        await message.answer("❌ Неверный пароль.")
        return await state.clear()

    role = await asyncio.to_thread(get_user_role, message.from_user.id)
    if role not in ['admin', 'owner']:
        return await message.answer("⛔ Нет в базе админов.")

    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔗 Создать ссылку"), KeyboardButton(text="👤 Статистика")],
        [KeyboardButton(text="🚪 Выйти")]
    ], resize_keyboard=True)
    
    await message.answer(f"✅ <b>Вход выполнен!</b>\nРоль: {role.upper()}", reply_markup=kb, parse_mode="HTML")
    await state.clear()

# ─────────────────── 2. АДМИН ПАНЕЛЬ ───────────────────

@router.message(F.text == "🚪 Выйти")
async def admin_logout(message: Message, state: FSMContext):
    await message.answer("🔒 Выход.", reply_markup=ReplyKeyboardRemove())
    await cmd_start(message, state)

@router.message(F.text == "🔗 Создать ссылку")
async def admin_get_link(message: Message):
    user_id = message.from_user.id
    if await asyncio.to_thread(get_user_role, user_id) == 'user': return

    try:
        # Генерируем ссылку с ЗАЯВКАМИ (creates_join_request=True)
        invite = await bot.create_chat_invite_link(
            chat_id=ALLOWED_GROUP,
            name=f"Adm {user_id}", 
            creates_join_request=True 
        )
        
        # Сохраняем (чтобы знать чья она)
        supabase.table("bot_admins").update({"personal_link": invite.invite_link}).eq("user_id", user_id).execute()
        
        await message.answer(
            f"✅ <b>Ваша ссылка готова!</b>\n\n{invite.invite_link}\n\n"
            "1. Кидайте её людям.\n2. Они подадут заявку.\n3. Бот пришлет заявку в админ-чат.", 
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(F.text == "👤 Статистика")
async def admin_stats(message: Message):
    uptime = str(datetime.timedelta(seconds=int(time.time() - START_TIME)))
    await message.answer(f"📊 <b>Статус:</b>\nUptime: {uptime}\nSupport: {len(active_support)}", parse_mode="HTML")

# ─────────────────── 3. ОБРАБОТКА ЗАЯВОК (В ГРУППУ) ───────────────────

@router.chat_join_request()
async def handle_join_request(update: ChatJoinRequest):
    """Прилетает, когда юзер переходит по ссылке и жмет 'Подать заявку'"""
    user = update.from_user
    invite_link = update.invite_link
    
    inviter_text = "Неизвестно"
    
    # Пытаемся узнать, чей это инвайт
    if invite_link:
        res = supabase.table("bot_admins").select("user_id").eq("personal_link", invite_link.invite_link).execute()
        if res.data:
            inviter_id = res.data[0]['user_id']
            inviter_text = f"Админа ID {inviter_id}"

    # Отправляем в админ-чат на ручное одобрение
    text = (
        f"🛎 <b>НОВАЯ ЗАЯВКА</b>\n\n"
        f"👤 <b>Кто:</b> {html.escape(user.full_name)} (ID: <code>{user.id}</code>)\n"
        f"🎫 <b>Ссылка:</b> {inviter_text}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_{user.id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_{user.id}")
    ]])
    
    await bot.send_message(ADMIN_CHAT, text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("approve_"))
async def approve_join(call: CallbackQuery):
    user_id = int(call.data.split("_")[1])
    admin_role = await asyncio.to_thread(get_user_role, call.from_user.id)
    
    if admin_role == 'user': return await call.answer("Нет прав.", show_alert=True)

    try:
        await bot.approve_chat_join_request(ALLOWED_GROUP, user_id)
        await bot.send_message(user_id, "🎉 <b>Ваша заявка одобрена!</b> Добро пожаловать.", parse_mode="HTML")
        await call.message.edit_text(f"{call.message.text}\n\n✅ ПРИНЯТ ({call.from_user.full_name})", reply_markup=None)
        
        # Регаем в базе
        log_action(call.from_user.id, "approve_request", user_id)
        # Получаем инфо о юзере через get_chat (так как в call его нет)
        try:
            u_info = await bot.get_chat(user_id)
            await asyncio.to_thread(upsert_user, user_id, u_info.username, u_info.full_name)
        except: pass
        
    except Exception as e:
        await call.answer(f"Ошибка: {e}", show_alert=True)

@router.callback_query(F.data.startswith("decline_"))
async def decline_join(call: CallbackQuery):
    user_id = int(call.data.split("_")[1])
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return

    try:
        await bot.decline_chat_join_request(ALLOWED_GROUP, user_id)
        await call.message.edit_text(f"{call.message.text}\n\n❌ ОТКЛОНЕН ({call.from_user.full_name})", reply_markup=None)
        log_action(call.from_user.id, "decline_request", user_id)
    except: pass

# ─────────────────── 4. АПЕЛЛЯЦИИ И ПОДДЕРЖКА ───────────────────

@router.callback_query(F.data == "make_appeal")
async def make_appeal(call: CallbackQuery):
    if call.from_user.id in appealing_users: return await call.answer("Уже пишите.", show_alert=True)
    appealing_users.add(call.from_user.id)
    await call.message.edit_text("✍ <b>Напишите причину разбана</b> одним сообщением.", parse_mode="HTML")

@router.callback_query(F.data.startswith("unban_"))
async def unban_user(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return
    target_id = int(call.data.split("_")[1])
    
    # База
    supabase.table("users").update({"ban_global": False}).eq("user_id", target_id).execute()
    # Телеграм (Iris)
    try: await bot.unban_chat_member(ALLOWED_GROUP, target_id, only_if_banned=True)
    except: pass
    
    try: await bot.send_message(target_id, "✅ <b>Вы разбанены!</b>", parse_mode="HTML")
    except: pass
    await call.message.edit_text(f"{call.message.text}\n\n✅ РАЗБАНЕН", reply_markup=None)

@router.callback_query(F.data == "req_support")
async def req_support(call: CallbackQuery):
    user_id = call.from_user.id
    if user_id in active_support: return await call.answer("Чат открыт.", show_alert=True)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Ответить", callback_data=f"chat_start_{user_id}")]])
    await bot.send_message(ADMIN_CHAT, f"🆘 <b>HELP</b>\n🆔 <code>{user_id}</code>", reply_markup=kb, parse_mode="HTML")
    await call.message.edit_text("⏳ Ждите админа.", parse_mode="HTML")

@router.callback_query(F.data.startswith("chat_start_"))
async def start_chat(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return
    user_id = int(call.data.split("_")[2])
    active_support.add(user_id)
    await bot.send_message(user_id, "👨‍💻 <b>Админ тут.</b> Пишите.", parse_mode="HTML")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⛔ Завершить", callback_data=f"chat_end_{user_id}")]])
    await call.message.edit_text(f"{call.message.text}\n\n✅ В РАБОТЕ", reply_markup=kb)

@router.callback_query(F.data.startswith("chat_end_"))
async def end_chat(call: CallbackQuery):
    user_id = int(call.data.split("_")[2])
    if user_id in active_support: active_support.remove(user_id)
    try: await bot.send_message(user_id, "✅ Диалог завершен.")
    except: pass
    await call.message.edit_text("🏁 Завершен.", reply_markup=None)

# ─────────────────── 5. ПЕРЕСЫЛКА И ЖАЛОБЫ ───────────────────

@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def private_msg(message: Message, state: FSMContext):
    if await state.get_state(): return # Если ввод пароля
    user_id = message.from_user.id
    
    # Апелляция
    if user_id in appealing_users:
        appealing_users.remove(user_id)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Разбанить", callback_data=f"unban_{user_id}"), InlineKeyboardButton(text="❌ Отказать", callback_data="ignore")]])
        await bot.send_message(ADMIN_CHAT, f"⚖️ <b>АПЕЛЛЯЦИЯ</b>\n🆔 {user_id}\n📄 {html.escape(message.text)}", reply_markup=kb, parse_mode="HTML")
        await message.answer("✅ Отправлено.")
        return

    # Поддержка
    if user_id in active_support:
        await bot.send_message(ADMIN_CHAT, f"📩 <b>User:</b>\n{message.text}", parse_mode="HTML")

@router.message(F.chat.id == ADMIN_CHAT, F.reply_to_message)
async def admin_reply(message: Message):
    try:
        if "User:" in (message.reply_to_message.text or "") or "ID:" in (message.reply_to_message.text or ""):
            import re
            found = re.search(r'ID:.*?(\d+)', message.reply_to_message.text) or re.search(r'🆔.*?(\d+)', message.reply_to_message.text)
            if found:
                await bot.send_message(int(found.group(1)), f"👨‍💻 <b>Админ:</b>\n{message.text}", parse_mode="HTML")
                await message.react([type('Emoji', (object,), {'emoji': '👍'})]) # Реакция если получится, или просто игнор
    except: pass

@router.message(F.reply_to_message, F.text.startswith((".жалоба", ".ж")), F.chat.type.in_({"supergroup", "group"}))
async def report(message: Message):
    if message.chat.id != ALLOWED_GROUP: return
    offender = message.reply_to_message.from_user
    text = f"<b>ЖАЛОБА</b>\n👮‍♂️ На: {offender.mention_html()}\n🔗 {message.reply_to_message.get_url()}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Взять", callback_data=f"take_{message.message_id}_{message.chat.id}")]])
    await bot.send_message(ADMIN_CHAT, text, reply_markup=kb, parse_mode="HTML")
    await message.delete()

@router.callback_query(F.data.startswith("take_"))
async def take_rep(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return
    msg_id = int(call.data.split("_")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Закрыть", callback_data=f"close_{msg_id}")]])
    await call.message.edit_text(f"{call.message.text}\n\n✅ Взял: {call.from_user.full_name}", reply_markup=kb)

@router.callback_query(F.data.startswith("close_"))
async def close_rep(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return
    await call.message.edit_text("🔒 Закрыто.")

# ─────────────────── СЕРВЕР И ЗАПУСК ───────────────────
dp.include_router(router)
async def health_check(request): return web.Response(text="Bot Alive")
async def start_server():
    app = web.Application(); app.router.add_get('/', health_check)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", 8080))).start()

async def main():
    # 🔥 РЕЗКИЙ СБРОС (Убивает старые сессии)
    await bot.delete_webhook(drop_pending_updates=True)
    
    await start_server()
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
