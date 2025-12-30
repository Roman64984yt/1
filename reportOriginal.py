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
ADMIN_PASSWORD = "1234"  # 🔐 ПАРОЛЬ ДЛЯ ВХОДА В АДМИНКУ
CREATOR_ID = 7240918914

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
appealing_users = set()

class AdminAuth(StatesGroup):
    waiting_for_password = State()

# ─────────────────── ФУНКЦИИ БАЗЫ ДАННЫХ ───────────────────

def upsert_user(tg_id, username, full_name):
    """Просто сохраняет юзера, не меняя роль"""
    try:
        data = {"user_id": tg_id, "username": username or "No Nickname", "full_name": full_name}
        supabase.table("users").upsert(data, on_conflict="user_id").execute()
    except: pass

def get_user_role(user_id):
    """🔥 ПРОВЕРКА РОЛИ ИЗ ТАБЛИЦЫ USERS"""
    if user_id == CREATOR_ID: return 'owner'
    try:
        res = supabase.table("users").select("role").eq("user_id", user_id).execute()
        if res.data: return res.data[0]['role'] # вернет 'admin', 'owner' или 'user'
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

# ─────────────────── 1. ГЛАВНОЕ МЕНЮ И АВТОРИЗАЦИЯ ───────────────────

@router.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    
    # Сохраняем в базу (если новый)
    asyncio.create_task(asyncio.to_thread(upsert_user, user.id, user.username, user.full_name))
    
    bans = await asyncio.to_thread(get_user_bans, user.id)
    if bans and bans.get("ban_global") is True:
        reason = bans.get("ban_reason") or "Нарушение правил"
        return await message.answer(f"⛔ <b>ВЫ ЗАБЛОКИРОВАНЫ.</b>\nПричина: {html.escape(reason)}", parse_mode="HTML")

    safe_name = html.escape(user.full_name)
    text = (
        f"👋 Привет, {safe_name}!\n\n"
        "Это бот для доступа в Quick Talk Chat.\n"
        "Для входа используйте ссылку от администратора."
    )
    
    # Меню без кнопки "Подать заявку", как ты просил
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 Авторизация (Админ)", callback_data="auth_admin")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="req_support")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "auth_admin")
async def auth_start(call: CallbackQuery, state: FSMContext):
    # Сначала проверяем роль в базе users
    role = await asyncio.to_thread(get_user_role, call.from_user.id)
    if role == 'user':
        return await call.answer("⛔ Вы не являетесь администратором!", show_alert=True)

    await call.message.delete()
    await call.message.answer("🔑 <b>Введите пароль доступа:</b>", parse_mode="HTML")
    await state.set_state(AdminAuth.waiting_for_password)

@router.message(AdminAuth.waiting_for_password)
async def auth_check(message: Message, state: FSMContext):
    if message.text.strip() != ADMIN_PASSWORD:
        await message.answer("❌ Неверный пароль.")
        return await state.clear()

    # Еще раз проверяем роль (защита)
    role = await asyncio.to_thread(get_user_role, message.from_user.id)
    if role not in ['admin', 'owner']:
        return await message.answer("⛔ Вас нет в базе (роль user).")

    # Админ-панель (кнопки внизу)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔗 Моя ссылка"), KeyboardButton(text="👤 Статус")],
        [KeyboardButton(text="🚪 Выйти")]
    ], resize_keyboard=True)
    
    await message.answer(f"✅ <b>Вход выполнен!</b>\nРоль: {role.upper()}", reply_markup=kb, parse_mode="HTML")
    await state.clear()

# ─────────────────── 2. АДМИНСКИЕ КНОПКИ ───────────────────

@router.message(F.text == "🚪 Выйти")
async def admin_logout(message: Message, state: FSMContext):
    await message.answer("🔒 Сеанс завершен.", reply_markup=ReplyKeyboardRemove())
    await cmd_start(message, state)

@router.message(F.text == "🔗 Моя ссылка")
async def admin_create_link(message: Message):
    user_id = message.from_user.id
    if await asyncio.to_thread(get_user_role, user_id) == 'user': return

    try:
        # 1. Проверяем, есть ли уже ссылка в таблице admin_links
        res = supabase.table("admin_links").select("link").eq("user_id", user_id).execute()
        
        if res.data and res.data[0].get('link'):
            existing = res.data[0]['link']
            await message.answer(f"🎫 <b>Ваша ссылка (активна):</b>\n{existing}\n\n<i>(Новая не создавалась)</i>", parse_mode="HTML")
            return

        # 2. Создаем новую с заявками
        invite = await bot.create_chat_invite_link(
            chat_id=ALLOWED_GROUP,
            name=f"Admin {user_id}", 
            creates_join_request=True 
        )
        
        # 3. Сохраняем в таблицу ссылок
        supabase.table("admin_links").upsert({"user_id": user_id, "link": invite.invite_link}).execute()
        log_action(user_id, "create_link")
        
        await message.answer(f"✅ <b>Ссылка готова!</b>\n{invite.invite_link}\n\nКидайте её людям.", parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(F.text == "👤 Статус")
async def admin_stats(message: Message):
    uptime = str(datetime.timedelta(seconds=int(time.time() - START_TIME)))
    await message.answer(f"📊 <b>Аптайм:</b> {uptime}", parse_mode="HTML")

# ─────────────────── 3. ОБРАБОТКА ЗАЯВОК (ИМЕННЫЕ) ───────────────────

@router.chat_join_request()
async def handle_join_request(update: ChatJoinRequest):
    """Срабатывает, когда юзер переходит по ссылке админа"""
    user = update.from_user
    invite_link = update.invite_link
    
    inviter_name = "Неизвестно"
    
    # Определяем чья ссылка
    if invite_link:
        # Ищем в таблице admin_links
        res = supabase.table("admin_links").select("user_id").eq("link", invite_link.invite_link).execute()
        if res.data:
            admin_id = res.data[0]['user_id']
            # Достаем имя админа из users
            u_res = supabase.table("users").select("username, full_name").eq("user_id", admin_id).execute()
            if u_res.data:
                adm = u_res.data[0]
                inviter_name = f"@{adm['username']}" if adm['username'] else adm['full_name']

    # Формируем сообщение в Админ-чат
    user_mention = f"@{user.username}" if user.username else user.full_name
    
    text = (
        f"🛎 <b>НОВАЯ ЗАЯВКА</b>\n\n"
        f"👤 <b>Кто:</b> {user_mention} (ID: {user.id})\n"
        f"🎫 <b>Ссылка от:</b> {inviter_name}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_{user.id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_{user.id}")
    ]])
    
    await bot.send_message(ADMIN_CHAT, text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("approve_"))
async def approve_join(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': 
        return await call.answer("Нет прав.", show_alert=True)

    user_id = int(call.data.split("_")[1])
    try:
        await bot.approve_chat_join_request(ALLOWED_GROUP, user_id)
        await call.message.edit_text(f"{call.message.text}\n\n✅ ПРИНЯТ ({call.from_user.full_name})", reply_markup=None)
        await bot.send_message(user_id, "🎉 <b>Заявка одобрена!</b> Добро пожаловать.", parse_mode="HTML")
        
        # Регаем юзера в базе
        try:
            chat_u = await bot.get_chat(user_id)
            await asyncio.to_thread(upsert_user, user_id, chat_u.username, chat_u.full_name)
        except: pass
        
        log_action(call.from_user.id, "approve", user_id)
    except Exception as e:
        await call.answer(f"Ошибка: {e}", show_alert=True)

@router.callback_query(F.data.startswith("decline_"))
async def decline_join(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return

    user_id = int(call.data.split("_")[1])
    try:
        await bot.decline_chat_join_request(ALLOWED_GROUP, user_id)
        await call.message.edit_text(f"{call.message.text}\n\n❌ ОТКЛОНЕН", reply_markup=None)
        log_action(call.from_user.id, "decline", user_id)
    except: pass

# ─────────────────── 4. ПОДДЕРЖКА ───────────────────

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
    await call.message.edit_text("⏳ <b>Запрос отправлен.</b>\nОжидайте администратора.", parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("chat_start_"))
async def start_support_chat(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user':
        return await call.answer("Только админы.", show_alert=True)

    user_id = int(call.data.split("_")[2])
    active_support.add(user_id)
    safe_admin_name = html.escape(call.from_user.full_name)

    try:
        await bot.send_message(user_id, "👨‍💻 <b>Администратор подключился!</b>\nТеперь вы можете писать сюда сообщения.", parse_mode="HTML")
    except:
        return await call.answer("Не могу написать юзеру.", show_alert=True)

    kb_end = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⛔ Завершить чат", callback_data=f"chat_end_{user_id}")]])
    await call.message.edit_text(
        f"{call.message.text}\n\n✅ <b>ЧАТ АКТИВЕН</b>\nАдмин: {safe_admin_name}",
        reply_markup=kb_end, parse_mode="HTML"
    )
    await call.answer("Чат начат!")

@router.callback_query(F.data.startswith("chat_end_"))
async def end_support_chat(call: CallbackQuery):
    user_id = int(call.data.split("_")[2])
    if user_id in active_support: active_support.remove(user_id)
    try: await bot.send_message(user_id, "✅ Диалог завершен администратором.")
    except: pass
    await call.message.edit_text(f"{call.message.text}\n\n🏁 <b>Чат завершен.</b>", reply_markup=None, parse_mode="HTML")

# ─────────────────── 5. ПЕРЕСЫЛКА И ЖАЛОБЫ ───────────────────

@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def user_message_handler(message: Message, state: FSMContext):
    if await state.get_state(): return # Если ввод пароля - не шлем

    user_id = message.from_user.id
    if user_id in active_support:
        safe_name = html.escape(message.from_user.full_name)
        safe_text = html.escape(message.text) if message.text else "[Файл/Медиа]"
        await bot.send_message(ADMIN_CHAT, f"📩 <b>Сообщение от юзера</b>\n🆔 ID: <code>{user_id}</code>\n👤 Имя: {safe_name}\n\n{safe_text}", parse_mode="HTML")

@router.message(F.chat.id == ADMIN_CHAT, F.reply_to_message)
async def admin_reply_handler(message: Message):
    try:
        txt = message.reply_to_message.text or ""
        if "📩" in txt and "ID:" in txt:
            import re
            found = re.search(r'ID:.*?(\d+)', txt)
            if found:
                uid = int(found.group(1))
                safe_reply = html.escape(message.text) if message.text else "[Файл]"
                await bot.send_message(uid, f"👨‍💻 <b>Админ:</b>\n{safe_reply}", parse_mode="HTML")
                await message.reply("✅")
    except: pass

@router.message(F.reply_to_message, F.text.startswith((".жалоба", ".ж")), F.chat.type.in_({"supergroup", "group"}))
async def handle_report(message: Message):
    if message.chat.id != ALLOWED_GROUP: return
    offender = message.reply_to_message.from_user
    reporter = message.from_user
    if offender.id == reporter.id: return await message.reply("На себя нельзя!")

    text = f"""
<b>ЖАЛОБА В ГРУППЕ</b>

👮‍♂️ <b>Нарушитель:</b> {offender.mention_html()}
👤 <b>Кто пожаловался:</b> {reporter.mention_html()}
🔗 <b>Ссылка:</b> {message.reply_to_message.get_url()}
    """.strip()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Принять жалобу", callback_data=f"take_{message.reply_to_message.message_id}_{reporter.id}_{message.chat.id}")
    ]])
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
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Закрыть жалобу ✅", callback_data=f"close_{msg_id}")]])
    await call.message.edit_text(f"{call.message.text}\n\n✅ <b>Взялся:</b> {call.from_user.full_name}", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("close_"))
async def close_complaint(call: CallbackQuery):
    if await asyncio.to_thread(get_user_role, call.from_user.id) == 'user': return
    await call.message.edit_text(f"{call.message.text}\n\n🔒 <b>Жалоба закрыта</b>", reply_markup=None, parse_mode="HTML")

# ─────────────────── 6. КОМАНДЫ (.рассылка, .инфо) ───────────────────

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

# ─────────────────── СЕРВЕР И ЗАПУСК ───────────────────
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
