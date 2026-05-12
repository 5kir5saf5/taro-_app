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
from aiohttp import web

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
    """Получает данные пользователя, создаёт если нет"""
    data = load_data()
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {
            "questions_left": 1,      # ← КЛЮЧЕВОЕ ПОЛЕ
            "last_free_date": None,
            "total_asked": 0
        }
        save_data(data)
        print(f"🆕 Создан новый пользователь {uid}: 1 вопрос")
    return data["users"][uid]

def update_user(user_id, key, value):
    """Обновляет поле пользователя"""
    data = load_data()
    uid = str(user_id)
    if uid not in data["users"]:
        get_user(user_id)
    data["users"][uid][key] = value
    save_data(data)
    print(f"📝 Обновлён пользователь {uid}: {key} = {value}")

def can_get_free(user_id):
    """Проверяет, можно ли дать бесплатный вопрос"""
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
    """Использовать бесплатный вопрос (возвращает True если успешно)"""
    if can_get_free(user_id):
        update_user(user_id, "last_free_date", datetime.now().isoformat())
        # Бесплатный вопрос не списывает из questions_left, а даёт +1 отдельно
        user = get_user(user_id)
        update_user(user_id, "questions_left", user["questions_left"] + 1)
        print(f"🎁 Пользователь {user_id} активировал бесплатный вопрос")
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
    "Шут", "Маг", "Верховная Жрица", "Императрица", "Император",
    "Иерофант", "Влюблённые", "Колесница", "Сила", "Отшельник",
    "Колесо Фортуны", "Справедливость", "Повешенный", "Смерть",
    "Умеренность", "Дьявол", "Башня", "Звезда", "Луна", "Солнце", "Суд", "Мир",
    "Туз Жезлов", "Двойка Жезлов", "Тройка Жезлов", "Четвёрка Жезлов",
    "Пятёрка Жезлов", "Шестёрка Жезлов", "Семёрка Жезлов", "Восьмёрка Жезлов",
    "Девятка Жезлов", "Десятка Жезлов", "Паж Жезлов", "Рыцарь Жезлов",
    "Королева Жезлов", "Король Жезлов",
    "Туз Кубков", "Двойка Кубков", "Тройка Кубков", "Четвёрка Кубков",
    "Пятёрка Кубков", "Шестёрка Кубков", "Семёрка Кубков", "Восьмёрка Кубков",
    "Девятка Кубков", "Десятка Кубков", "Паж Кубков", "Рыцарь Кубков",
    "Королева Кубков", "Король Кубков",
    "Туз Мечей", "Двойка Мечей", "Тройка Мечей", "Четвёрка Мечей",
    "Пятёрка Мечей", "Шестёрка Мечей", "Семёрка Мечей", "Восьмёрка Мечей",
    "Девятка Мечей", "Десятка Мечей", "Паж Мечей", "Рыцарь Мечей",
    "Королева Мечей", "Король Мечей",
    "Туз Пентаклей", "Двойка Пентаклей", "Тройка Пентаклей", "Четвёрка Пентаклей",
    "Пятёрка Пентаклей", "Шестёрка Пентаклей", "Семёрка Пентаклей", "Восьмёрка Пентаклей",
    "Девятка Пентаклей", "Десятка Пентаклей", "Паж Пентаклей", "Рыцарь Пентаклей",
    "Королева Пентаклей", "Король Пентаклей"
]

# =========================
# AI ФУНКЦИЯ
# =========================
async def get_ai_tarot_reading(question, category):
    selected_card = random.choice(all_cards)
    is_reversed = random.choice([True, False])
    position = "перевёрнутая" if is_reversed else "прямая"
    
    system_prompt = """Ты — таролог. Отвечай на русском, 3-4 абзаца. Пиши от первого лица.
Будь мудрым, эмпатичным, но по делу. Дай ответ на вопрос человека и короткий совет."""
    
    category_names = {
        "love": "любовь и отношения",
        "money": "финансы и деньги",
        "career": "карьеру и работу",
        "general": "общую ситуацию"
    }
    
    user_prompt = f"""Выпавшая карта: {selected_card}
Положение: {position}
Тема: {category_names.get(category, 'общая ситуация')}
Вопрос: {question}

Напиши трактовку этой карты применительно к вопросу. 3-4 абзаца. В конце короткий совет."""
    
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
                max_tokens=600
            )
        )
        ai_text = response.choices[0].message.content
        return f"🃏 **{selected_card}** ({position})\n\n{ai_text}"
    except Exception as e:
        print(f"AI ошибка: {e}")
        return None

# =========================
# КЛАВИАТУРЫ
# =========================
main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🌟 Спросить судьбу", callback_data="ask")],
    [InlineKeyboardButton(text="💎 Мой баланс", callback_data="balance")],
    [InlineKeyboardButton(text="🎁 Бесплатный вопрос", callback_data="free")],
    [InlineKeyboardButton(text="💰 Купить вопросы", callback_data="buy")],
    [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
])

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
# ВЕБ-СЕРВЕР ДЛЯ ПИНГА
# =========================
async def health_check(request):
    return web.Response(text="✅ Bot is alive!", status=200)

async def start_web_app():
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port=int(os.environ.get('PORT', 8080)))
    await site.start()
    print("✅ Health check сервер запущен")

# =========================
# ОБРАБОТЧИКИ
# =========================
@dp.message(CommandStart())
async def start(message: types.Message):
    uid = message.from_user.id
    user = get_user(uid)
    print(f"📊 Старт пользователя {uid}: баланс = {user['questions_left']}")
    await message.answer(
        "🔮 **Добро пожаловать в Таро Уэйта** 🔮\n\n"
        "В моей колоде 78 карт. Каждый расклад уникален.\n\n"
        "✨ **Как гадать:**\n"
        "1. Выбери категорию\n"
        "2. Задай вопрос\n"
        "3. Я вытяну карту и растолкую её\n\n"
        "🎁 **1 бесплатный вопрос при регистрации!**\n\n"
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
        "📖 **Как пользоваться**\n\n"
        "🌟 **Спросить судьбу** — выбери тему и задай вопрос\n"
        "💎 **Баланс** — сколько вопросов осталось\n"
        "🎁 **Бесплатный вопрос** — 1 раз в день\n"
        "💰 **Купить вопросы** — пополнить баланс\n\n"
        "**Оплата:**\n"
        "Карта Тинькофф: `2200 7019 2912 3708`\n"
        "В комментарии укажи свой Telegram ID\n"
        "Отправь скрин чека — администратор начислит вопросы\n\n"
        "Вопросы и поддержка: @support",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery):
    uid = callback.from_user.id
    user = get_user(uid)
    print(f"📊 Баланс {uid}: {user['questions_left']}")
    await callback.message.edit_text(
        f"💎 **Твой баланс**\n\n"
        f"🎴 Осталось вопросов: **{user['questions_left']}**\n"
        f"📆 Всего раскладов: {user.get('total_asked', 0)}\n"
        f"🎁 Бесплатный вопрос: {'✅ доступен' if can_get_free(uid) else '❌ использован сегодня'}\n\n"
        f"✨ **Совет:** Чем больше вопросов, тем глубже понимание своей судьбы.",
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
            "Выбери категорию 👇",
            reply_markup=category_menu,
            parse_mode="Markdown"
        )
        await state.set_state(TarotState.waiting_category)
        await state.update_data(is_free=True)
    else:
        await callback.message.edit_text(
            "❌ Бесплатный вопрос уже использован сегодня.\n\n"
            "Вернись завтра или купи вопросы — они недорогие, а ответы того стоят.",
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
    await state.update_data(is_free=False)
    await callback.answer()

@dp.callback_query(F.data.startswith("cat_"))
async def category_chosen(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("cat_", "")
    await state.update_data(category=category)
    
    category_names = {
        "love": "💕 Любовь и отношения",
        "money": "💰 Деньги и финансы",
        "career": "💼 Карьера и работа",
        "general": "🔮 Общий вопрос"
    }
    
    await callback.message.edit_text(
        f"📝 **Тема: {category_names[category]}**\n\n"
        f"Напиши свой вопрос.\n\n"
        f"**Примеры:**\n"
        f"• Что меня ждёт в любви?\n"
        f"• Как ко мне относится Анна?\n"
        f"• Стоит ли менять работу?\n\n"
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
    
    # Получаем актуальные данные пользователя
    user = get_user(uid)
    print(f"📊 Перед списанием: пользователь {uid}, баланс = {user['questions_left']}, is_free = {is_free}")
    
    # Проверка баланса (только для платных вопросов)
    if not is_free and user["questions_left"] <= 0:
        await message.answer(
            "❌ **Закончились вопросы!**\n\n"
            "Но ты всегда можешь:\n"
            "• Взять **бесплатный вопрос** (1 раз в день)\n"
            "• **Купить вопросы** — это недорого\n\n"
            "3 вопроса — 50 ₽\n"
            "8 вопросов — 100 ₽\n"
            "15 вопросов — 350 ₽\n\n"
            "Нажми «Купить вопросы» в главном меню 💎",
            reply_markup=main_menu,
            parse_mode="Markdown"
        )
        await state.clear()
        return
    
    # Списываем вопрос (только для платных)
    remaining = user["questions_left"]
    if not is_free:
        remaining = user["questions_left"] - 1
        update_user(uid, "questions_left", remaining)
        update_user(uid, "total_asked", user.get("total_asked", 0) + 1)
        print(f"✅ Списано: пользователь {uid}, новый баланс = {remaining}")
    else:
        print(f"🎁 Бесплатный вопрос: пользователь {uid}, баланс не меняется")
    
    # Отправляем статус
    await bot.send_chat_action(uid, action="typing")
    
    # Получаем AI-ответ
    msg = await message.answer("🔮 *Перемешиваю колоду...*\n🃏 *Вытягиваю карту...*\n🌙 *Карта говорит...*\n\n", parse_mode="Markdown")
    
    reading = await get_ai_tarot_reading(question, category)
    
    if reading:
        final_text = f"✨ **Ваш расклад** ✨\n\n{reading}\n\n"
        
        # Мягкий призыв купить вопросы
        if not is_free:
            final_text += f"📊 Осталось вопросов: {remaining}\n"
            
            if remaining <= 2:
                final_text += f"\n💎 *Хотите узнать больше? Загляните в раздел «Купить вопросы» — там недорого.*\n"
            elif remaining <= 5:
                final_text += f"\n✨ *Судьба готовит ещё ответы. Пополните баланс, чтобы не прерывать диалог.*\n"
        else:
            final_text += f"\n🎁 *Это был ваш бесплатный расклад. Нужно больше? Купите вопросы — они недорогие!*\n"
        
        final_text += f"\n💫 *Судьба в твоих руках — карты лишь подсвечивают путь.*"
        
        await msg.edit_text(final_text, parse_mode="Markdown", reply_markup=main_menu)
    else:
        await msg.edit_text(
            "🌙 *Карты молчат...*\n\n"
            "Попробуй переформулировать вопрос или загляни позже.",
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
        "💳 **Реквизиты для оплаты:**\n"
        "Карта Тинькофф: `2200 7019 2912 3708`\n"
        "В комментарии к переводу укажи свой Telegram ID\n\n"
        "📸 После оплаты отправь скрин чека сюда\n"
        "Администратор начислит вопросы вручную\n\n"
        "⏳ Обычно это занимает несколько часов.",
        reply_markup=tariff_keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith(("3_50", "8_100", "15_350")))
async def tariff_chosen(callback: CallbackQuery):
    qty_map = {"3_50": 3, "8_100": 8, "15_350": 15}
    qty = qty_map[callback.data]
    price_map = {"3_50": "50", "8_100": "100", "15_350": "350"}
    price = price_map[callback.data]
    
    await callback.message.edit_text(
        f"✅ Ты выбрал **{qty} вопросов** за **{price} ₽**\n\n"
        f"💳 **Как оплатить:**\n"
        f"1. Переведи **{price} ₽** на карту `2200 7019 2912 3708` (Тинькофф)\n"
        f"2. В комментарии укажи: `{callback.from_user.id}`\n"
        f"3. Отправь скрин чека в этот чат\n\n"
        f"🔔 Администратор проверит и начислит вопросы.\n"
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
        "Администратор проверит оплату и начислит вопросы.\n"
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
        "/all_users — список пользователей\n"
        "/give_free `ID` — дать бесплатный вопрос\n"
        "/admin — помощь",
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
        await bot.send_message(uid, f"🎉 **Вопросы начислены!**\n\nАдминистратор добавил **{qty} вопросов**.\nТвой баланс: **{new_bal}**.\n\nБлагодарим за оплату! 🌙", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка. Формат: `/add_questions ID КОЛИЧЕСТВО`", parse_mode="Markdown")

@dp.message(Command("give_free"))
async def give_free_cmd(message: types.Message):
    """Админ может дать бесплатный вопрос любому пользователю"""
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split()
        uid = int(parts[1])
        user = get_user(uid)
        new_bal = user["questions_left"] + 1
        update_user(uid, "questions_left", new_bal)
        await message.answer(f"✅ Добавлен 1 бесплатный вопрос пользователю `{uid}`. Новый баланс: {new_bal}", parse_mode="Markdown")
        await bot.send_message(uid, f"🎁 **Бесплатный вопрос!**\n\nАдминистратор добавил вам **1 вопрос** в подарок!\nТвой баланс: **{new_bal}**.\n\nПриятного гадания 🌙", parse_mode="Markdown")
    except:
        await message.answer("❌ Ошибка. Формат: `/give_free ID`", parse_mode="Markdown")

@dp.message(Command("all_users"))
async def all_users_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    data = load_data()
    if not data["users"]:
        await message.answer("📊 Нет пользователей")
        return
    text = "📊 **Пользователи:**\n\n"
    for uid, info in data["users"].items():
        text += f"🆔 `{uid}`: {info['questions_left']} воп. / всего {info.get('total_asked',0)}\n"
        if len(text) > 3500:
            await message.answer(text[:4000], parse_mode="Markdown")
            text = ""
    if text:
        await message.answer(text[:4000], parse_mode="Markdown")

@dp.message(Command("reset_all"))
async def reset_all_cmd(message: types.Message):
    """Сброс всех данных (только для админа, осторожно!)"""
    if message.from_user.id != ADMIN_ID:
        return
    save_data({"users": {}})
    await message.answer("⚠️ **Все данные сброшены!** Все пользователи удалены.", parse_mode="Markdown")

# =========================
# ЗАПУСК
# =========================
async def main():
    await start_web_app()
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот Таро с 78 картами и корректным балансом запущен!")
    print(f"👑 Админ ID: {ADMIN_ID}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
