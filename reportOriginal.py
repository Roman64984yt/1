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
from aiogram.filters import Command, ChatMemberUpdatedFilter, MEMBER
from aiohttp import web
from supabase import create_client, Client

load_dotenv()

# ─────────────────── КОНФИГУРАЦИЯ ───────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = "1234"  # 🔐 ПАРОЛЬ ОТ АДМИНКИ
CREATOR_ID = 7240918914

# Настройки чатов
ADMIN_CHAT = -1003408598270      
ALLOWED_GROUP = -1003344194941   

SUPABASE_URL = "https://tvriklnmvrqstgnyxhry.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR2cmlrbG5tdnJxc3Rnbnl4aHJ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU4MjcyNTAsImV4cCI6MjA4MTQwMzI1MH0.101vOltGd1N30c4whqs8nY6K0nuE9LsMFqYCKCANFRQ"

if not BOT_TOKEN: exit("NO TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ База подключена")
except: print("❌ Ошибка БД")

START_TIME = time.time()
active_support = set()
pending_requests = set()
appealing_users = set()
user_invites = {} # Для старых заявок через бота

class AdminAuth(StatesGroup):
    waiting_for_password = State()

# ─────────────────── ФУНКЦИИ БАЗЫ ───────────────────

def upsert_user(tg_id, username, full_name):
    try:
        data = {"user_id": tg_id, "username": username or "No Nickname", "full_name": full_name}
        supabase.table("users").upsert(data, on_conflict="user_id").execute()
    except: pass

def get_user_role(user_id):
    """Проверка роли СТРОГО из таблицы users"""
    if user_id == CREATOR_ID: return 'owner'
    try:
        res = supabase.table("users").select("role").eq("user_id", user_id).execute()
        if res.data: return res.data[0]['role']
    except: pass
    return 'user'

def get_user_bans(user_id):
    try:
        res = supabase.table("users").select("ban_global, ban_requests, ban_support, ban_reason").eq("user_id", user_id).execute()
        if res.data: return res.data[0]
    except: return None

def log_action(admin_id, action, target_id=None, details=''):
    try:
        supabase.table("admin_logs").insert({
            "admin_id": admin_id, "action": action, 
            "target_id": target_id, "details": details
        }).execute()
    except: pass

# ─────────────────── 1. МЕНЮ (/start) ───────────────────

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
        "Это бот для доступа в закрытый чат.\n"
        "Вы внесены в базу данных.\n\n"
        "Выберите действие ниже:"
    )
    # Вернул старый набор кнопок + Авторизация
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Подать заявку на вход", callback_data="req_join")],
        [InlineKeyboardButton(text="🔐 Авторизация (Админ)", callback_data="auth_admin")],
        [InlineKeyboardButton(text="🆘 Поддержка (Связь с админом)", callback_data="req_support")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# ─────────────────── 2. СТАРЫЕ ЗАЯВКИ (ЧЕРЕЗ БОТА) ───────────────────

@router.callback_query(F.data == "req_join")
async def join_request_handler(call: CallbackQuery):
    user_id = call.from_user.id
    bans = await asyncio.to_thread(get_user_bans, user_id)
    if bans and (bans.get("ban_global") is True or bans.get("ban_requests") is True):
        return await call.answer("⛔ Вам запрещено подавать заявки!", show_alert=True)

    if user_id in pending_requests:
        return await call.answer("⏳ Ваша заявка уже на рассмотрении.", show_alert=True)

    pending_requests.add(user_id)
    await call.message.edit_text("✅ <b>Заявка отправлена!</b>\nЖдите решения админа.", parse_mode="HTML")

    safe_name = html.escape(call.from_user.full_name)
    username = f"@{call.from_user.username}" if call.from_user.username else "нет ника"
    
    text_admin = (
        f"🛎 <b>НОВАЯ ЗАЯВКА НА ВХОД</b>\n\n"
        f"👤 <b>Кто:</b> {safe_name} ({username})\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Пустить (24ч)", callback_data=f"invite_yes_{user_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"invite_no_{user_id}")
    ]])
    await bot.send_message(ADMIN_CHAT, text_admin, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("invite_"))
async def process_invite_decision(call: CallbackQuery):
    # Разрешаем Владельцу и Админам
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user':
        return await call.answer("⛔ Только Админ!", show_alert=True)

    action = call.data.split("_")[1]
    user_id = int(call.data.split("_")[2])

    if user_id in pending_requests: pending_requests.remove(user_id)
    
    safe_admin_name = html.escape(call.from_user.full_name)

    if action == "yes":
        try:
            invite = await bot.create_chat_invite_link(
                chat_id=ALLOWED_GROUP,
                name=f"User {user_id}",
                member_limit=1,
                expire_date=datetime.timedelta(hours=24)
            )
            user_invites[user_id] = invite.invite_link
            
            await bot.send_message(user_id, f"🎉 <b>Добро пожаловать!</b>\n\nВот ссылка (24 часа):\n{invite.invite_link}", parse_mode="HTML")
            await call.message.edit_text(f"{call.message.text}\n\n✅ ОДОБРЕНО ({safe_admin_name})", reply_markup=None)
            log_action(call.from_user.id, "invite_approve_bot", user_id)
        except Exception as e:
            await call.answer(f"Ошибка: {e}", show_alert=True)
    elif action == "no":
        try: await bot.send_message(user_id, "⛔ Ваша заявка отклонена.", parse_mode="HTML")
        except: pass
        await call.message.edit_text(f"{call.message.text}\n\n❌ ОТКЛОНЕНО ({safe_admin_name})", reply_markup=None)
        log_action(call.from_user.id, "invite_reject_bot", user_id)
    
    await call.answer()

@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def on_user_join(event: ChatMemberUpdated):
    user_id = event.from_user.id
    if user_id in user_invites:
        try: await bot.revoke_chat_invite_link(chat_id=event.chat.id, invite_link=user_invites[user_id])
        except: pass
        del user_invites[user_id]

# ─────────────────── 3. АВТОРИЗАЦИЯ И ССЫЛКИ ───────────────────

@router.callback_query(F.data == "auth_admin")
async def auth_start(call: CallbackQuery, state: FSMContext):
    role = await asyncio.to_thread(get_user_role, call.from_user.id)
    if role == 'user': return await call.answer("⛔ Вы не администратор!", show_alert=True)

    await call.message.delete()
    await call.message.answer("🔑 <b>Введите пароль:</b>", parse_mode="HTML")
    await state.set_state(AdminAuth.waiting_for_password)

@router.message(AdminAuth.waiting_for_password)
async def auth_check(message: Message, state: FSMContext):
    if message.text.strip() != ADMIN_PASSWORD:
        await message.answer("❌ Неверный пароль.")
        return await state.clear()

    role = await asyncio.to_thread(get_user_role, message.from_user.id)
    if role not in ['admin', 'owner']: return await message.answer("⛔ Ошибка прав.")

    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔗 Моя ссылка"), KeyboardButton(text="👤 Статус")],
        [KeyboardButton(text="🚪 Выйти")]
    ], resize_keyboard=True)
    
    await message.answer(f"✅ <b>Вход выполнен!</b>", reply_markup=kb, parse_mode="HTML")
    await state.clear()

@router.message(F.text == "🚪 Выйти")
async def admin_logout(message: Message, state: FSMContext):
    await message.answer("🔒 Выход.", reply_markup=ReplyKeyboardRemove())
    await cmd_start(message, state)

@router.message(F.text == "👤 Статус")
async def admin_stats(message: Message):
    uptime = str(datetime.timedelta(seconds=int(time.time() - START_TIME)))
    await message.answer(f"📊 <b>Аптайм:</b> {uptime}", parse_mode="HTML")

@router.message(F.text == "🔗 Моя ссылка")
async def admin_create_link(message: Message):
    user_id = message.from_user.id
    if await asyncio.to_thread(get_user_role, user_id) == 'user': return

    try:
        res = supabase.table("admin_links").select("link").eq("user_id", user_id).execute()
        if res.data and res.data[0].get('link'):
            await message.answer(f"🎫 <b>Ваша ссылка:</b>\n{res.data[0]['link']}", parse_mode="HTML")
            return

        invite = await bot.create_chat_invite_link(chat_id=ALLOWED_GROUP, name=f"Admin {user_id}", creates_join_request=True)
        supabase.table("admin_links").upsert({"user_id": user_id, "link": invite.invite_link}).execute()
        await message.answer(f"✅ <b>Ссылка создана!</b>\n{invite.invite_link}", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.chat_join_request()
async def handle_join_request(update: ChatJoinRequest):
    user = update.from_user
    invite_link = update.invite_link
    inviter_name = "Неизвестно"
    
    if invite_link:
        res = supabase.table("admin_links").select("user_id").eq("link", invite_link.invite_link).execute()
        if res.data:
            admin_id = res.data[0]['user_id']
            u_res = supabase.table("users").select("username, full_name").eq("user_id", admin_id).execute()
            if u_res.data:
                adm = u_res.data[0]
                inviter_name = f"@{adm['username']}" if adm['username'] else adm['full_name']

    user_mention = f"@{user.username}" if user.username else user.full_name
    text = f"🛎 <b>ЗАЯВКА (ЧЕРЕЗ ССЫЛКУ)</b>\n\n👤 <b>Кто:</b> {user_mention} (ID: {user.id})\n🎫 <b>Пригласил:</b> {inviter_name}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_{user.id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_{user.id}")
    ]])
    await bot.send_message(ADMIN_CHAT, text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("approve_"))
async def approve_link_user(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return
    user_id = int(call.data.split("_")[1])
    try:
        await bot.approve_chat_join_request(ALLOWED_GROUP, user_id)
        await call.message.edit_text(f"{call.message.text}\n\n✅ ПРИНЯТ", reply_markup=None)
        await bot.send_message(user_id, "🎉 <b>Заявка одобрена!</b> Добро пожаловать.", parse_mode="HTML")
        try:
            u = await bot.get_chat(user_id)
            await asyncio.to_thread(upsert_user, user_id, u.username, u.full_name)
        except: pass
        log_action(call.from_user.id, "approve_link", user_id)
    except: await call.answer("Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("decline_"))
async def decline_link_user(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return
    user_id = int(call.data.split("_")[1])
    try:
        await bot.decline_chat_join_request(ALLOWED_GROUP, user_id)
        await call.message.edit_text(f"{call.message.text}\n\n❌ ОТКЛОНЕН", reply_markup=None)
    except: pass

# ─────────────────── 4. ПОДДЕРЖКА (КАК БЫЛО) ───────────────────

@router.callback_query(F.data == "req_support")
async def request_support_handler(call: CallbackQuery):
    user_id = call.from_user.id
    bans = await asyncio.to_thread(get_user_bans, user_id)
    if bans and bans.get("ban_support") is True:
        return await call.answer("⛔ Вам запрещено писать в поддержку!", show_alert=True)

    if user_id in active_support:
        return await call.answer("У вас уже открыт чат.", show_alert=True)

    safe_name = html.escape(call.from_user.full_name)
    text_admin = f"🆘 <b>ЗАПРОС В ПОДДЕРЖКУ</b>\n\n👤 <b>От:</b> {safe_name}\n🆔 <b>ID:</b> <code>{user_id}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Начать чат", callback_data=f"chat_start_{user_id}")
    ]])
    await bot.send_message(ADMIN_CHAT, text_admin, reply_markup=kb, parse_mode="HTML")
    await call.message.edit_text("⏳ <b>Запрос отправлен.</b>", parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("chat_start_"))
async def start_support_chat(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return await call.answer("Только админы.", show_alert=True)
    user_id = int(call.data.split("_")[2])
    active_support.add(user_id)
    safe_admin_name = html.escape(call.from_user.full_name)

    try: await bot.send_message(user_id, "👨‍💻 <b>Администратор подключился!</b>", parse_mode="HTML")
    except: return await call.answer("Не могу написать юзеру (блок?)", show_alert=True)

    kb_end = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⛔ Завершить чат", callback_data=f"chat_end_{user_id}")]])
    await call.message.edit_text(f"{call.message.text}\n\n✅ <b>ЧАТ АКТИВЕН</b>\nАдмин: {safe_admin_name}", reply_markup=kb_end, parse_mode="HTML")
    await call.answer("Чат начат!")

@router.callback_query(F.data.startswith("chat_end_"))
async def end_support_chat(call: CallbackQuery):
    user_id = int(call.data.split("_")[2])
    if user_id in active_support: active_support.remove(user_id)
    try: await bot.send_message(user_id, "✅ Диалог завершен администратором.")
    except: pass
    await call.message.edit_text(f"{call.message.text}\n\n🏁 <b>Чат завершен.</b>", reply_markup=None, parse_mode="HTML")

# ─────────────────── 5. ПЕРЕСЫЛКА СООБЩЕНИЙ ───────────────────

@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def user_message_handler(message: Message, state: FSMContext):
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
        safe_name = html.escape(message.from_user.full_name)
        safe_text = html.escape(message.text) if message.text else "[Файл/Медиа]"
        await bot.send_message(ADMIN_CHAT, f"📩 <b>Сообщение от юзера</b>\n🆔 ID: <code>{user_id}</code>\n👤 Имя: {safe_name}\n\n{safe_text}", parse_mode="HTML")
    else:
        # Игнорим или меню (как в старом коде)
        if user_id not in pending_requests: pass

@router.message(F.chat.id == ADMIN_CHAT, F.reply_to_message)
async def admin_reply_handler(message: Message):
    try:
        txt = message.reply_to_message.text or ""
        if "📩" in txt and "ID:" in txt:
            import re
            found = re.search(r'ID:.*?(\d+)', txt) or re.search(r'🆔.*?(\d+)', txt)
            if found:
                uid = int(found.group(1))
                safe_reply = html.escape(message.text) if message.text else "[Файл]"
                await bot.send_message(uid, f"👨‍💻 <b>Админ:</b>\n{safe_reply}", parse_mode="HTML")
                await message.reply("✅")
    except: pass

# ─────────────────── 6. ЖАЛОБЫ (.ж) ───────────────────

@router.message(F.reply_to_message, F.text.startswith((".жалоба", ".ж")), F.chat.type.in_({"supergroup", "group"}))
async def handle_report(message: Message):
    if message.chat.id != ALLOWED_GROUP: return
    offender = message.reply_to_message.from_user
    reporter = message.from_user
    if offender.id == reporter.id: return await message.reply("На себя нельзя!")
    
    text = f"<b>ЖАЛОБА</b>\n👮‍♂️ <b>На:</b> {offender.mention_html()}\n👤 <b>От:</b> {reporter.mention_html()}\n🔗 {message.reply_to_message.get_url()}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Принять", callback_data=f"take_{message.message_id}_{reporter.id}_{message.chat.id}")]])
    
    await bot.send_message(ADMIN_CHAT, text, reply_markup=kb, parse_mode="HTML")
    await message.delete()
    m = await message.answer(f"{reporter.mention_html()}, жалоба отправлена!", parse_mode="HTML")
    await asyncio.sleep(5)
    try: await m.delete()
    except: pass

@router.callback_query(F.data.startswith("take_"))
async def take_complaint(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return
    msg_id = int(call.data.split("_")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Закрыть ✅", callback_data=f"close_{msg_id}")]])
    await call.message.edit_text(f"{call.message.text}\n\n✅ <b>Взялся:</b> {call.from_user.full_name}", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("close_"))
async def close_complaint(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return
    await call.message.edit_text(f"{call.message.text}\n\n🔒 <b>Жалоба закрыта</b>", reply_markup=None, parse_mode="HTML")

# ─────────────────── 7. РАССЫЛКА И АПЕЛЛЯЦИЯ ───────────────────

@router.message(F.text == ".рассылка", F.chat.id == ADMIN_CHAT)
async def send_info_broadcast(message: Message):
    if await asyncio.to_thread(get_user_role, message.from_user.id) == 'user': return
    
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
Попросите ссылку у администратора.

🔮 <b>Развлечения:</b>
Шар судьбы (Да/Нет):
<code>.инфо Ваш вопрос</code>
    """
    await bot.send_message(ALLOWED_GROUP, info_text, parse_mode="HTML")
    await message.reply("✅")

@router.callback_query(F.data == "make_appeal")
async def make_appeal(call: CallbackQuery):
    if call.from_user.id in appealing_users: return await call.answer("Уже пишите.", show_alert=True)
    appealing_users.add(call.from_user.id)
    await call.message.edit_text("✍ <b>Напишите причину разбана</b> одним сообщением.", parse_mode="HTML")

@router.callback_query(F.data.startswith("unban_"))
async def unban_user(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return
    target_id = int(call.data.split("_")[1])
    supabase.table("users").update({"ban_global": False}).eq("user_id", target_id).execute()
    try: await bot.unban_chat_member(ALLOWED_GROUP, target_id, only_if_banned=True)
    except: pass
    try: await bot.send_message(target_id, "✅ <b>Вы разбанены!</b>", parse_mode="HTML")
    except: pass
    await call.message.edit_text(f"{call.message.text}\n\n✅ РАЗБАНЕН", reply_markup=None)

@router.message(F.text.lower().startswith(".инфо"), F.chat.id.in_({ALLOWED_GROUP, ADMIN_CHAT}))
async def magic_ball(message: Message):
    answers = ["✅ Да", "❌ Нет", "⚠️ Рискованно", "🤔 50/50", "👀 Попробуй"]
    await message.reply(f"🔮 {random.choice(answers)}")

@router.message(F.text.lower() == "бот", F.chat.id == ADMIN_CHAT)
async def bot_status(message: Message):
    uptime = str(datetime.timedelta(seconds=int(time.time() - START_TIME)))
    await message.answer(f"🤖 OK\nUp: {uptime}", parse_mode="HTML")

@router.message(F.text.startswith((".админ", ".admin")), F.chat.id == ALLOWED_GROUP)
async def call_admin(message: Message):
    await message.answer("Админы вызваны!")
    await bot.send_message(ADMIN_CHAT, f"🚨 ВЫЗОВ!\n{message.get_url()}")

# ─────────────────── СЕРВЕР ───────────────────
dp.include_router(router)
async def health_check(request): return web.Response(text="Bot Alive")
async def start_server():
    app = web.Application(); app.router.add_get('/', health_check)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", 8080))).start()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await start_server()
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
