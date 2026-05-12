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
    return {"users": {}, "pending_payments": []}

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

# =========================
# СОВЕТЫ
# =========================
tips = [
    "🌙 Доверься своей интуиции — она ведёт тебя правильным путём.",
    "✨ Вселенная всегда на твоей стороне, даже если сейчас кажется иначе.",
    "💫 Сделай паузу и прислушайся к тишине — в ней скрыты ответы.",
    "🔥 Не бойся перемен — они открывают новые двери.",
    "🍃 Отпусти контроль и позволь потоку нести себя.",
]

# =========================
# КАРТЫ ТАРО (только названия, трактовки берутся из AI)
# =========================
card_names = [
    "Шут", "Маг", "Верховная Жрица", "Императрица", "Император",
    "Иерофант", "Влюбленные", "Колесница", "Сила", "Отшельник",
    "Колесо Фортуны", "Справедливость", "Повешенный", "Смерть",
    "Умеренность", "Дьявол", "Башня", "Звезда", "Луна", "Солнце", "Суд", "Мир",
    "Туз Жезлов", "Туз Кубков", "Туз Мечей", "Туз Пентаклей"
]

# =========================
# AI ФУНКЦИЯ
# =========================
async def get_ai_meaning(card_name, position, question, theme):
    """Получает трактовку карты от AI"""
    system_prompt = """Ты — мудрый таролог с большим опытом. Отвечай на русском языке, 3-4 абзаца. 
Будь глубоким, эмпатичным и честным. Используй образы и метафоры. 
Дай совет в конце. Не повторяйся, будь уникальным для каждого вопроса."""
    
    user_prompt = f"""Сделай трактовку карты Таро.

Карта: {card_name}
Положение: {position} (прямая или перевёрнутая)
Тема: {theme}
Вопрос пользователя: {question}

Опиши, что эта карта значит для человека. Дай мудрый совет. Пиши от первого лица как таролог."""
    
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
                max_tokens=650
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI ошибка: {e}")
        return f"✨ Карта {card_name} в {position} положении говорит о важных переменах в твоём вопросе. Прислушайся к себе — ответ уже внутри тебя."

# =========================
# КЛАВИАТУРЫ
# =========================
main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔮 Получить ответ", callback_data="ask")],
    [InlineKeyboardButton(text="❤️ Любовь", callback_data="love")],
    [InlineKeyboardButton(text="💰 Финансы", callback_data="money")],
    [InlineKeyboardButton(text="💼 Карьера", callback_data="career")],
    [InlineKeyboardButton(text="🎁 Бесплатный вопрос дня", callback_data="free")],
    [InlineKeyboardButton(text="💎 Купить вопросы", callback_data="buy")],
    [InlineKeyboardButton(text="📊 Мой баланс", callback_data="balance")],
])

back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
])

tariff_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔮 3 вопроса — 50 ₽", callback_data="3_50")],
    [InlineKeyboardButton(text="✨ 8 вопросов — 100 ₽", callback_data="8_100")],
    [InlineKeyboardButton(text="🌟 15 вопросов — 350 ₽", callback_data="15_350")],
    [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
])

# =========================
# ОБРАБОТЧИКИ
# =========================
@dp.message(CommandStart())
async def start(message: types.Message):
    uid = message.from_user.id
    get_user(uid)
    await message.answer(
        "🔮 **Добро пожаловать в AI-Таро** 🔮\n\n"
        "Я — древний оракул, оживлённый силой искусственного интеллекта.\n"
        "Каждая карта говорит именно о твоей ситуации.\n\n"
        "✨ **Преимущества:**\n"
        "• Уникальная трактовка под твой вопрос\n"
        "• Глубокие, живые ответы\n"
        "• Бесплатный вопрос каждый день\n\n"
        "Задай вопрос и получи ответ, который попадёт в самое сердце ❤️\n\n"
        "Выбери тему или расклад 👇",
        reply_markup=main_keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔮 Главное меню — выбери действие:",
        reply_markup=main_keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "balance")
async def balance(callback: CallbackQuery):
    uid = callback.from_user.id
    user = get_user(uid)
    await callback.message.edit_text(
        f"📊 **Твой баланс**\n\n"
        f"🎴 Осталось вопросов: **{user['questions_left']}**\n"
        f"📆 Всего раскладов: {user.get('total_asked', 0)}\n"
        f"🎁 Бесплатный вопрос: {'доступен' if can_get_free(uid) else 'использован сегодня'}\n\n"
        f"➕ Пополнить баланс — кнопка «Купить вопросы»",
        reply_markup=back_keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "free")
async def free_question(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if use_free_question(uid):
        await callback.message.edit_text(
            "🎁 **Бесплатный вопрос дня активирован!**\n\n"
            "Напиши свой вопрос:",
            reply_markup=back_keyboard
        )
        await state.set_state(TarotState.waiting_question)
        await state.update_data(theme="general")
    else:
        await callback.message.edit_text(
            "❌ Ты уже использовал бесплатный вопрос сегодня.\n"
            "Вернись завтра или купи платные вопросы.",
            reply_markup=back_keyboard
        )
    await callback.answer()

@dp.callback_query(F.data.in_(["love", "money", "career", "ask"]))
async def theme_choose(callback: CallbackQuery, state: FSMContext):
    theme_map = {"love": "любовь и отношения", "money": "финансы и деньги", "career": "карьеру и работу", "ask": "общую ситуацию"}
    theme = callback.data
    await state.update_data(theme=theme)
    await callback.message.edit_text(
        f"📝 **Тема: {theme_map[theme]}**\n\n"
        f"Напиши свой вопрос:\n\n"
        f"Примеры:\n"
        f"• Что меня ждёт в любви?\n"
        f"• Как ко мне относится Имя?\n"
        f"• Стоит ли менять работу?",
        reply_markup=back_keyboard
    )
    await state.set_state(TarotState.waiting_question)
    await callback.answer()

@dp.message(TarotState.waiting_question)
async def ask_tarot(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    data = await state.get_data()
    theme = data.get("theme", "general")
    question = message.text.strip()
    
    user = get_user(uid)
    if user["questions_left"] <= 0:
        await message.answer(
            "❌ У тебя закончились вопросы!\nПополни баланс в меню.",
            reply_markup=main_keyboard
        )
        await state.clear()
        return
    
    # Списываем вопрос
    new_balance = user["choices_left"] - 1
    update_user(uid, "choices_left", new_balance)
    update_user(uid, "total_asked", user.get("total_asked", 0) + 1)
    
    # Выбираем случайную карту
    card_name = random.choice(card_names)
    is_reversed = random.choice([True, False])
    position = "перевёрнутая" if is_reversed else "прямая"
    
    # Отправляем статус "печатает"
    await bot.send_chat_action(uid, action="typing")
    
    # Получаем AI-трактовку
    meaning = await get_ai_meaning(card_name, position, question, theme)
    
    tip = random.choice(tips)
    
    text = f"""
🃏 **Карта:** {card_name} ({position})

{meaning}

💫 **Совет дня:** {tip}

📊 **Осталось вопросов:** {new_balance}
    """
    
    await message.answer(text, parse_mode="Markdown", reply_markup=main_keyboard)
    await state.clear()

# =========================
# ПОКУПКА И АДМИН
# =========================
@dp.callback_query(F.data == "buy")
async def buy_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "💸 **Выбери пакет вопросов:**\n\n"
        "🔮 3 вопроса — 50 ₽\n"
        "✨ 8 вопросов — 100 ₽\n"
        "🌟 15 вопросов — 350 ₽\n\n"
        "💳 **Реквизиты Тинькофф:** `89512694834`\n"
        "В комментарии укажи свой Telegram ID.\n\n"
        "📸 После оплаты отправь скрин чека сюда — администратор начислит вопросы.",
        reply_markup=tariff_keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith(("3_50", "8_100", "15_350")))
async def tariff_chosen(callback: CallbackQuery):
    qty_map = {"3_50": 3, "8_100": 8, "15_350": 15}
    qty = qty_map[callback.data]
    price = {"3_50": "50", "8_100": "100", "15_350": "350"}[callback.data]
    await callback.message.edit_text(
        f"✅ Ты выбрал **{qty} вопросов** за {price} ₽.\n\n"
        f"💳 Переведи {price} ₽ на номер `89512694834` (Тинькофф)\n"
        f"✍️ В комментарии укажи: «Таро {qty}» и свой ID: `{callback.from_user.id}`\n\n"
        f"📸 После оплаты отправь скрин чека сюда.\n\n"
        f"🔔 Администратор проверит и начислит вопросы вручную.",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(F.photo)
async def payment_screenshot(message: types.Message):
    uid = message.from_user.id
    await message.answer(
        "📸 Спасибо, скрин получен!\n\n"
        "Администратор проверит оплату и начислит вопросы в ближайшее время.",
        reply_markup=main_keyboard
    )
    if ADMIN_ID:
        await bot.send_message(
            ADMIN_ID,
            f"💰 Новый скрин чека от @{message.from_user.username} (ID: {uid})\n"
            f"Начисли вопросы командой: `/add_questions {uid} КОЛИЧЕСТВО`"
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
        "/admin — эта помощь"
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
        await bot.send_message(uid, f"🎉 Администратор начислил тебе {qty} вопросов! Твой баланс: {new_bal}. Благодарим за оплату ✨")
    except:
        await message.answer("❌ Формат: `/add_questions ID КОЛИЧЕСТВО`")

@dp.message(Command("all_users"))
async def all_users_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    data = load_data()
    text = "📊 **Пользователи:**\n\n"
    for uid, info in data["users"].items():
        text += f"👤 `{uid}`: {info['questions_left']} в. / {info.get('total_asked',0)} всего\n"
    await message.answer(text[:4000], parse_mode="Markdown")

# =========================
# ЗАПУСК
# =========================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ AI-Таро бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())