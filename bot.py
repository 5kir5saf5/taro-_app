import asyncio
import os
import random
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from openai import OpenAI
from functools import partial

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# AI настройки
DEEPSEEK_API_KEY = "sk-TGlDfSmzTbMDtSHpMNJqiSPQcWybM9hrfbGDS8ICPJUgDwIQ"
DEEPSEEK_BASE_URL = "https://api.chatanywhere.tech/v1"

deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# =========================
# ФАЙЛ ДАННЫХ
# =========================
DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(user_id):
    data = load_data()
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {
            "questions_left": 1,
            "last_free_date": None,
            "total_asked": 0
        }
        save_data(data)
    return data["users"][uid]

def update_user(user_id, key, value):
    data = load_data()
    uid = str(user_id)
    if uid not in data["users"]:
        get_user(user_id)
    data["users"][uid][key] = value
    save_data(data)

def can_get_free(user_id):
    user = get_user(user_id)
    last = user.get("last_free_date")
    if not last:
        return True
    try:
        last_date = datetime.fromisoformat(last)
        return datetime.now() - last_date >= timedelta(days=1)
    except:
        return True

def use_free_question(user_id):
    if can_get_free(user_id):
        update_user(user_id, "last_free_date", datetime.now().isoformat())
        return True
    return False

# =========================
# СОСТОЯНИЯ
# =========================
class TarotState(StatesGroup):
    waiting_question = State()
    waiting_category = State()

# =========================
# ВСЕ 78 КАРТ ТАРО УЭЙТА
# =========================
all_cards = [
    # Старшие арканы (22)
    "Шут", "Маг", "Верховная Жрица", "Императрица", "Император",
    "Иерофант", "Влюблённые", "Колесница", "Сила", "Отшельник",
    "Колесо Фортуны", "Справедливость", "Повешенный", "Смерть",
    "Умеренность", "Дьявол", "Башня", "Звезда", "Луна", "Солнце", "Суд", "Мир",
    # Жезлы (14)
    "Туз Жезлов", "Двойка Жезлов", "Тройка Жезлов", "Четвёрка Жезлов",
    "Пятёрка Жезлов", "Шестёрка Жезлов", "Семёрка Жезлов", "Восьмёрка Жезлов",
    "Девятка Жезлов", "Десятка Жезлов", "Паж Жезлов", "Рыцарь Жезлов",
    "Королева Жезлов", "Король Жезлов",
    # Кубки (14)
    "Туз Кубков", "Двойка Кубков", "Тройка Кубков", "Четвёрка Кубков",
    "Пятёрка Кубков", "Шестёрка Кубков", "Семёрка Кубков", "Восьмёрка Кубков",
    "Девятка Кубков", "Десятка Кубков", "Паж Кубков", "Рыцарь Кубков",
    "Королева Кубков", "Король Кубков",
    # Мечи (14)
    "Туз Мечей", "Двойка Мечей", "Тройка Мечей", "Четвёрка Мечей",
    "Пятёрка Мечей", "Шестёрка Мечей", "Семёрка Мечей", "Восьмёрка Мечей",
    "Девятка Мечей", "Десятка Мечей", "Паж Мечей", "Рыцарь Мечей",
    "Королева Мечей", "Король Мечей",
    # Пентакли (14)
    "Туз Пентаклей", "Двойка Пентаклей", "Тройка Пентаклей", "Четвёрка Пентаклей",
    "Пятёрка Пентаклей", "Шестёрка Пентаклей", "Семёрка Пентаклей", "Восьмёрка Пентаклей",
    "Девятка Пентаклей", "Десятка Пентаклей", "Паж Пентаклей", "Рыцарь Пентаклей",
    "Королева Пентаклей", "Король Пентаклей"
]

# =========================
# AI ФУНКЦИЯ ДЛЯ РАСКЛАДА
# =========================
async def get_ai_tarot_reading(question, category):
    """Получает полный виртуальный расклад от AI"""
    
    system_prompt = """Ты — потомственный таролог с 30-летним стажем. 
Ты работаешь с колодой Таро Уэйта (78 карт). 
Отвечай на русском языке, очень развёрнуто, 5-7 абзацев. Создай атмосферу настоящего гадания.

Структура ответа:
1. Напиши, какую карту ты вытянул (название карты и её положение — прямое или перевёрнутое)
2. Дай глубокое описание карты и её символики
3. Раскрой значение карты применительно к вопросу пользователя
4. Добавь мудрый совет
5. Закончи вдохновляющей фразой

Пиши так, будто ты реально гадаешь человеку напротив. Будь эмпатичным, но честным. Используй образы и метафоры."""
    
    category_map = {
        "love": "любовь и отношения",
        "money": "финансы и деньги",
        "career": "карьеру и работу",
        "general": "общую жизненную ситуацию"
    }
    
    user_prompt = f"""Сделай полный таро-расклад на тему: {category_map.get(category, 'общая ситуация')}.

Вопрос пользователя: {question}

Выбери случайную карту из колоды Таро Уэйта (78 карт) и сделай её трактовку так, будто ты вытянул её сейчас. Карта может быть как прямой, так и перевёрнутой.

Напиши ответ от первого лица как таролог."""
    
    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            partial(
                deepseek_client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.85,
                max_tokens=1200
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI ошибка: {e}")
        return None

# =========================
# НОВЫЕ КНОПКИ (ГЛАВНОЕ МЕНЮ)
# =========================
main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🌟 Спросить судьбу", callback_data="ask")],
    [InlineKeyboardButton(text="💎 Мой баланс", callback_data="balance")],
    [InlineKeyboardButton(text="🎁 Бесплатный вопрос", callback_data="free")],
    [InlineKeyboardButton(text="💰 Купить вопросы", callback_data="buy")],
    [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
])

# Меню категорий (после нажатия "Спросить судьбу")
category_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💕 Любовь и отношения", callback_data="cat_love")],
    [InlineKeyboardButton(text="💰 Деньги и финансы", callback_data="cat_money")],
    [InlineKeyboardButton(text="💼 Карьера и работа", callback_data="cat_career")],
    [InlineKeyboardButton(text="🔮 Общий вопрос", callback_data="cat_general")],
    [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")],
])

back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_main")]
])

tariff_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔮 3 вопроса — 50 ₽", callback_data="3_50")],
    [InlineKeyboardButton(text="✨ 8 вопросов — 100 ₽", callback_data="8_100")],
    [InlineKeyboardButton(text="🌟 15 вопросов — 350 ₽", callback_data="15_350")],
    [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")],
])

# =========================
# ОБРАБОТЧИКИ
# =========================
@dp.message(CommandStart())
async def start(message: types.Message):
    uid = message.from_user.id
    get_user(uid)
    await message.answer(
        "🔮 **Добро пожаловать в AI-Таро Уэйта** 🔮\n\n"
        "Я — виртуальный таролог с доступом ко всем 78 картам Таро.\n"
        "Каждый расклад — уникален, потому что его создаёт искусственный интеллект,\n"
        "обученный на тысячах трактовок.\n\n"
        "✨ **Как это работает:**\n"
        "1. Выбери категорию вопроса\n"
        "2. Напиши, что тебя волнует\n"
        "3. Я вытяну карту и сделаю полный расклад\n\n"
        "🎁 **1 бесплатный вопрос каждый день!**\n\n"
        "Начни прямо сейчас 👇",
        reply_markup=main_menu,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔮 **Главное меню**\n\nВыбери действие:",
        reply_markup=main_menu,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "help")
async def help_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "📖 **Помощь**\n\n"
        "🌟 **Спросить судьбу** — выбери категорию и задай вопрос\n"
        "💎 **Баланс** — сколько вопросов осталось\n"
        "🎁 **Бесплатный вопрос** — один вопрос в день бесплатно\n"
        "💰 **Купить вопросы** — 3/8/15 вопросов за 50/100/350₽\n\n"
        "**Как оплатить:**\n"
        "Переведи сумму на Тинькофф **89512694834**\n"
        "В комментарии укажи свой Telegram ID\n"
        "Отправь скрин чеда сюда — администратор начислит вопросы\n\n"
        "По всем вопросам: @support",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery):
    uid = callback.from_user.id
    user = get_user(uid)
    await callback.message.edit_text(
        f"💎 **Твой баланс**\n\n"
        f"🎴 Осталось вопросов: **{user['questions_left']}**\n"
        f"📆 Всего раскладов: {user.get('total_asked', 0)}\n"
        f"🎁 Бесплатный вопрос: {'✅ доступен' if can_get_free(uid) else '❌ использован сегодня'}\n\n"
        f"Пополнить баланс — кнопка «Купить вопросы»",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "free")
async def free_question(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if use_free_question(uid):
        await callback.message.edit_text(
            "🎁 **Бесплатный вопрос активирован!**\n\n"
            "Сначала выбери категорию 👇",
            reply_markup=category_menu,
            parse_mode="Markdown"
        )
        await state.set_state(TarotState.waiting_category)
    else:
        await callback.message.edit_text(
            "❌ Ты уже использовал бесплатный вопрос сегодня.\n"
            "Вернись завтра или купи платные вопросы.",
            reply_markup=back_keyboard,
            parse_mode="Markdown"
        )
    await callback.answer()

@dp.callback_query(F.data == "ask")
async def ask_question(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📂 **Выбери категорию вопроса:**\n\n"
        "От этого зависит, на чём сфокусируется расклад 👇",
        reply_markup=category_menu,
        parse_mode="Markdown"
    )
    await state.set_state(TarotState.waiting_category)
    await callback.answer()

@dp.callback_query(F.data.startswith("cat_"))
async def category_chosen(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("cat_", "")
    await state.update_data(category=category, is_free=False)
    
    category_names = {
        "love": "💕 Любовь и отношения",
        "money": "💰 Деньги и финансы",
        "career": "💼 Карьера и работа",
        "general": "🔮 Общий вопрос"
    }
    
    await callback.message.edit_text(
        f"📝 **Категория: {category_names[category]}**\n\n"
        f"Теперь напиши свой вопрос.\n\n"
        f"**Примеры хороших вопросов:**\n"
        f"• Что меня ждёт в любви в ближайшее время?\n"
        f"• Как ко мне относится Анна?\n"
        f"• Стоит ли менять работу?\n"
        f"• Какие возможности для заработка у меня появятся?\n\n"
        f"Чем точнее вопрос — тем точнее ответ 🌙",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(TarotState.waiting_question)
    await callback.answer()

@dp.message(TarotState.waiting_question)
async def process_question(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    data = await state.get_data()
    category = data.get("category", "general")
    is_free = data.get("is_free", False)
    
    question = message.text.strip()
    
    # Проверка баланса
    user = get_user(uid)
    if not is_free and user["questions_left"] <= 0:
        await message.answer(
            "❌ У тебя закончились вопросы!\n\n"
            "Пополни баланс в главном меню (кнопка «Купить вопросы»).\n"
            "Или используй бесплатный вопрос (1 раз в день).",
            reply_markup=main_menu,
            parse_mode="Markdown"
        )
        await state.clear()
        return
    
    # Списываем вопрос (если не бесплатный)
    if not is_free:
        new_balance = user["questions_left"] - 1
        update_user(uid, "questions_left", new_balance)
        update_user(uid, "total_asked", user.get("total_asked", 0) + 1)
    
    # Отправляем статус "печатает"
    await bot.send_chat_action(uid, action="typing")
    
    # Получаем AI-расклад
    await message.answer("🔮 *Раскладываю карты...*\n🌙 *Карты говорят...*\n\n", parse_mode="Markdown")
    
    reading = await get_ai_tarot_reading(question, category)
    
    if reading:
        # Форматируем ответ
        final_text = f"✨ **Виртуальный расклад Таро** ✨\n\n{reading}\n\n"
        
        if not is_free:
            final_text += f"\n📊 *Осталось вопросов:* {new_balance}"
        else:
            final_text += f"\n🎁 *Бесплатный вопрос дня использован*\nВернись завтра!"
        
        final_text += f"\n\n💫 *Судьба в твоих руках — карты лишь подсвечивают путь.*"
        
        await message.answer(final_text, parse_mode="Markdown", reply_markup=main_menu)
    else:
        await message.answer(
            "🌙 *Карты молчат...*\n\nПопробуй переформулировать вопрос или задай его позже.\n\nМожет быть, Вселенной нужно время, чтобы ответить.",
            parse_mode="Markdown",
            reply_markup=main_menu
        )
    
    await state.clear()

# =========================
# ПОКУПКА
# =========================
@dp.callback_query(F.data == "buy")
async def buy_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "💎 **Выбери пакет вопросов** 💎\n\n"
        "🔮 **3 вопроса** — 50 ₽\n"
        "✨ **8 вопросов** — 100 ₽\n"
        "🌟 **15 вопросов** — 350 ₽\n\n"
        "💳 **Реквизиты Тинькофф:** `89512694834`\n"
        "📌 В комментарии к переводу укажи свой Telegram ID\n\n"
        "📸 После оплаты отправь скрин чека сюда — администратор начислит вопросы\n\n"
        "⏳ Обычно это занимает до нескольких часов.",
        reply_markup=tariff_keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith(("3_50", "8_100", "15_350")))
async def tariff_chosen(callback: CallbackQuery, state: FSMContext):
    qty_map = {"3_50": 3, "8_100": 8, "15_350": 15}
    qty = qty_map[callback.data]
    price_map = {"3_50": "50", "8_100": "100", "15_350": "350"}
    price = price_map[callback.data]
    
    await state.update_data(pending_qty=qty)
    
    await callback.message.edit_text(
        f"✅ Ты выбрал **{qty} вопросов** за **{price} ₽**\n\n"
        f"💳 **Инструкция по оплате:**\n"
        f"1. Переведи **{price} ₽** на номер карты `2200 7019 2912 3708` (Тинькофф)\n"
        f"2. В комментарии к переводу укажи: **«Таро {qty}»** и свой ID: `{callback.from_user.id}`\n"
        f"3. После перевода сделай скрин чека\n"
        f"4. Отправь скрин в этот чат\n\n"
        f"🔔 Администратор проверит оплату и начислит вопросы.\n\n"
        f"Спасибо за доверие! 🌙",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(F.photo)
async def payment_screenshot(message: types.Message):
    uid = message.from_user.id
    username = message.from_user.username or "без username"
    
    await message.answer(
        "📸 **Скрин получен!**\n\n"
        "Администратор проверит оплату в ближайшее время и начислит вопросы.\n"
        "Обычно это занимает несколько часов.\n\n"
        "Если оплата не пришла в течение суток — напиши @support.",
        reply_markup=main_menu,
        parse_mode="Markdown"
    )
    
    if ADMIN_ID:
        await bot.send_photo(
            ADMIN_ID,
            photo=message.photo[-1].file_id,
            caption=f"💰 **Новый скрин чека**\n\n"
                    f"👤 Пользователь: @{username}\n"
                    f"🆔 ID: `{uid}`\n\n"
                    f"📝 Команда для начисления:\n"
                    f"`/add_questions {uid} КОЛИЧЕСТВО`"
        )

# =========================
# АДМИН-КОМАНДЫ
# =========================
@dp.message(Command("admin"))
async def admin_help(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "👑 **Админ-панель**\n\n"
        "/add_questions `ID` `кол-во` — начислить вопросы\n"
        "/all_users — список всех пользователей\n"
        "/admin — эта помощь\n\n"
        "Пример: `/add_questions 123456789 10`",
        parse_mode="Markdown"
    )

@dp.message(Command("add_questions"))
async def add_questions_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split()
        uid = int(parts[1])
        qty = int(parts[2])
        user = get_user(uid)
        new_bal = user["questions_left"] + qty
        update_user(uid, "questions_left", new_bal)
        await message.answer(f"✅ Добавлено {qty} вопросов пользователю `{uid}`. Новый баланс: {new_bal}", parse_mode="Markdown")
        await bot.send_message(uid, f"🎉 **Вопросы начислены!**\n\nАдминистратор добавил тебе **{qty} вопросов**.\nТвой баланс: **{new_bal}**.\n\nБлагодарим за оплату! 🌙", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка. Формат: `/add_questions ID КОЛИЧЕСТВО`", parse_mode="Markdown")

@dp.message(Command("all_users"))
async def all_users_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    data = load_data()
    if not data["users"]:
        await message.answer("📊 Нет пользователей")
        return
    text = "📊 **Список пользователей:**\n\n"
    for uid, info in data["users"].items():
        text += f"🆔 `{uid}`: {info['questions_left']} вопросов / всего {info.get('total_asked',0)}\n"
        if len(text) > 3500:
            await message.answer(text[:4000], parse_mode="Markdown")
            text = ""
    if text:
        await message.answer(text[:4000], parse_mode="Markdown")

# =========================
# ЗАПУСК
# =========================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ AI-Таро бот с 78 картами запущен!")
    print(f"👑 Админ ID: {ADMIN_ID}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
