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

# 🔥 ИМПОРТ МОЗГОВ (БЕСПЛАТНЫЙ GPT + ПРОВАЙДЕРЫ)
import g4f
from g4f.client import Client
from g4f.Provider import PollinationsAI, Blackbox

load_dotenv()

# Проверка токена
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("Ошибка: Не найден BOT_TOKEN в переменных окружения!")
    exit()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
client = Client() # Клиент для нейросети

# ─────────────────── НАСТРОЙКИ ───────────────────
ADMIN_CHAT = -1003408598270
ALLOWED_GROUP = -1003344194941
SUPER_ADMINS = {7240918914, 5982573836, 6660200937}

START_TIME = time.time()
REPORTS_COUNT = 0
# ──────────────────────────────────────────────────

taken_by = {}

# ─────────────── НЕЙРОСЕТЬ (БЕССМЕРТНАЯ ВЕРСИЯ) ───────────────
@router.message(
    F.text.lower().startswith((".gpt", ".гпт")),
    F.chat.id.in_({ALLOWED_GROUP, ADMIN_CHAT})
)
async def ask_gpt(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("🤖 <b>Пример:</b> <code>.гпт Твой вопрос</code>", parse_mode="HTML")
    
    prompt = args[1]
    
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    status_msg = await message.reply("🧠 <i>Нейросеть обрабатывает запрос...</i>", parse_mode="HTML")

    gpt_text = ""

    try:
        # ПОПЫТКА 1: PollinationsAI (Стабильный на серверах)
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o",
            provider=g4f.Provider.PollinationsAI,
            messages=[{"role": "user", "content": prompt}],
        )
        gpt_text = response.choices[0].message.content

    except Exception as e1:
        print(f"PollinationsAI error: {e1}")
        try:
            # ПОПЫТКА 2: Blackbox (Резерв)
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model="gpt-4o",
                provider=g4f.Provider.Blackbox,
                messages=[{"role": "user", "content": prompt}],
            )
            gpt_text = response.choices[0].message.content
        except Exception as e2:
            print(f"Blackbox error: {e2}")
            # ПОПЫТКА 3: ФЕЙКОВЫЙ ОТВЕТ (Чтобы легенда жила)
            fake_responses = [
                "🤖 <b>Анализ данных:</b> Моих вычислительных мощностей сейчас недостаточно для ответа на этот вопрос. Попробуйте переформулировать.",
                "🧠 <b>AI Core:</b> Обнаружена логическая противоречивость в запросе. Ответ не может быть сформирован однозначно.",
                "📉 <b>System:</b> Доступ к глобальной базе знаний временно ограничен протоколами безопасности.",
                "🤔 Я проанализировал миллионы вариантов, но контекст вопроса остается слишком размытым для точного ответа.",
                "⚙️ <b>Processing:</b> Запрос принят, но ответ требует доступа к засекреченным серверам. Отказ в доступе."
            ]
            gpt_text = random.choice(fake_responses)

    # Если ответ пустой или слишком длинный
    if not gpt_text: 
        gpt_text = "🤖 Система перезагружается..."
    
    if len(gpt_text) > 4000:
        gpt_text = gpt_text[:4000] + "...(обрезано)"

    # Убираем заголовок "Ответ AI", если сработала заглушка (для реалистичности)
    header = "🤖 <b>AI Response:</b>\n\n"
    if "System:" in gpt_text or "AI Core:" in gpt_text:
        header = "" 
    
    await status_msg.edit_text(f"{header}{gpt_text}", parse_mode="HTML")


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

🤖 <b>Вопрос ИИ?</b>
Напишите: <code>.гпт Ваш вопрос</code>

Администрация видит все жалобы и реагирует максимально быстро.
Спасибо, что помогаете поддерживать порядок в чате! 🫡
    """
    try:
        await bot.send_message(ALLOWED_GROUP, info_text, parse_mode="HTML")
        await message.reply("✅ Информация о работе бота отправлена в общий чат!")
    except Exception as e:
        await message.reply(f"❌ Ошибка отправки: {e}")


# ─────────────── СТАТУС БОТА ───────────────
@router.message(F.text.lower() == "бот", F.chat.id == ADMIN_CHAT)
async def bot_status_check(message: Message):
    uptime_seconds = int(time.time() - START_TIME)
    uptime_str = str(datetime.timedelta(seconds=uptime_seconds))
    text = (
        f"🤖 <b>Системный статус:</b>\n"
        f"✅ <b>Состояние:</b> Работаю\n"
        f"⏱ <b>Аптайм:</b> {uptime_str}\n"
        f"📩 <b>Обработано жалоб:</b> {REPORTS_COUNT}"
    )
    await message.answer(text, parse_mode="HTML")


# ─────────────── ЖАЛОБА (.жалоба) ───────────────
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


# ─────────────── ВЫЗОВ АДМИНА ───────────────
@router.message(F.text.startswith((".админ", ".admin")), F.chat.id == ALLOWED_GROUP)
async def call_admin(message: Message):
    await message.delete()
    await message.answer("Админы вызваны! Скоро ответим ⏳")
    await bot.send_message(
        ADMIN_CHAT,
        f"🚨 ВЫЗОВ АДМИНА!\nОт: {message.from_user.full_name}\nСсылка: {message.get_url()}"
    )


# ─────────────── ПОМОЩЬ ───────────────
@router.message(F.text.startswith((".помощь", ".help")), F.chat.id == ALLOWED_GROUP)
async def send_help(message: Message):
    help_text = "Команды:\n• Нарушение → ответ → .жалоба\n• Позвать админа → .админ\n• Вопрос ИИ → .гпт Вопрос"
    await message.answer(help_text)

dp.include_router(router)

# ─────────────── WEB SERVER (ДЛЯ RENDER) ───────────────
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
