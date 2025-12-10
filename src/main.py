import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Получаем токен из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения. Создайте .env файл с BOT_TOKEN=ваш_токен")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Путь к файлу с вопросами
QUESTIONS_FILE = Path(__file__).parent.parent / "data" / "QUESTIONS_BASE.json"

# Загружаем вопросы из JSON
def load_questions() -> List[Dict]:
    """Загружает вопросы из JSON файла"""
    with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# Состояния FSM
class TestStates(StatesGroup):
    waiting_for_answer = State()
    question_selection = State()

# Глобальная переменная для хранения вопросов
questions_data = load_questions()

def get_question_by_number(question_num: int) -> Optional[Dict]:
    """Получает вопрос по номеру (1-60)"""
    if 1 <= question_num <= len(questions_data):
        return questions_data[question_num - 1]
    return None

def get_question_key(question_num: int) -> str:
    """Возвращает ключ вопроса (question1, question2, ...)"""
    return f"question{question_num}"

def create_answer_keyboard(answers: List[str], question_num: int, mode: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру с вариантами ответов"""
    buttons = []
    for idx, answer in enumerate(answers):
        callback_data = f"answer_{question_num}_{idx}_{mode}"
        # Telegram ограничивает текст кнопки до 64 символов
        # Показываем максимально возможный текст на кнопке
        # Полный текст уже виден в сообщении с вопросом выше
        if len(answer) <= 64:
            # Если текст помещается - показываем полностью
            button_text = answer
        else:
            # Если текст длинный - показываем начало (максимум 64 символа)
            button_text = answer[:61] + "..."
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
    
    # Добавляем кнопку возврата в меню
    buttons.append([InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_question_selection_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора вопроса (1-60)"""
    buttons = []
    # Создаем кнопки по 5 в ряд
    for i in range(0, 60, 5):
        row = []
        for j in range(5):
            num = i + j + 1
            if num <= 60:
                row.append(InlineKeyboardButton(text=str(num), callback_data=f"select_q_{num}"))
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает главное меню с выбором режима"""
    buttons = [
        [InlineKeyboardButton(text="📝 Сплошная сессия", callback_data="mode_continuous")],
        [InlineKeyboardButton(text="🔍 Выбор вопроса", callback_data="mode_select")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать решать", callback_data="start_test")]
    ])
    await message.answer(
        "👋 Добро пожаловать в бота для подготовки к экзамену!\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "start_test")
async def start_test(callback: CallbackQuery):
    """Обработчик кнопки 'Начать решать'"""
    await callback.message.edit_text(
        "Выберите режим тестирования:",
        reply_markup=create_main_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки возврата в меню"""
    await state.clear()
    await callback.message.edit_text(
        "Выберите режим тестирования:",
        reply_markup=create_main_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "mode_continuous")
async def mode_continuous(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора режима 'Сплошная сессия'"""
    await state.update_data(current_question=1, mode="continuous")
    await show_question(callback, 1, "continuous", state)
    await callback.answer()

@dp.callback_query(F.data == "mode_select")
async def mode_select(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора режима 'Выбор вопроса'"""
    await callback.message.edit_text(
        "Выберите номер вопроса (1-60):",
        reply_markup=create_question_selection_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("select_q_"))
async def select_question(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора конкретного вопроса"""
    question_num = int(callback.data.split("_")[-1])
    await state.update_data(current_question=question_num, mode="select")
    await show_question(callback, question_num, "select", state)
    await callback.answer()

async def show_question(callback: CallbackQuery, question_num: int, mode: str, state: FSMContext):
    """Показывает вопрос с вариантами ответов"""
    question_data = get_question_by_number(question_num)
    
    if not question_data:
        await callback.message.edit_text("❌ Вопрос не найден!")
        return
    
    question_key = get_question_key(question_num)
    question_text = question_data.get(question_key, "")
    answers = question_data.get("answers", [])
    
    if not question_text or not answers:
        await callback.message.edit_text("❌ Ошибка загрузки вопроса!")
        return
    
    # Формируем текст сообщения с полными вариантами ответов
    text = f"❓ <b>Вопрос {question_num}:</b>\n\n{question_text}\n\n"
    text += "<b>Варианты ответов:</b>\n"
    for answer in answers:
        text += f"\n{answer}\n"
    
    keyboard = create_answer_keyboard(answers, question_num, mode)
    
    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("answer_"))
async def handle_answer(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора ответа"""
    parts = callback.data.split("_")
    question_num = int(parts[1])
    answer_idx = int(parts[2])
    mode = parts[3]
    
    question_data = get_question_by_number(question_num)
    
    if not question_data:
        await callback.answer("❌ Ошибка!")
        return
    
    answers = question_data.get("answers", [])
    correct_answer = question_data.get("correct_answer", "")
    
    if answer_idx >= len(answers):
        await callback.answer("❌ Ошибка!")
        return
    
    selected_answer = answers[answer_idx]
    is_correct = selected_answer == correct_answer
    
    await callback.answer()
    
    # В зависимости от режима и правильности ответа показываем результат
    if mode == "continuous":
        # Режим сплошной сессии
        if is_correct:
            # Правильный ответ - автоматически переходим к следующему
            response_text = "✅ Молодец! Правильный ответ!"
            await callback.message.edit_text(
                response_text,
                parse_mode="HTML"
            )
            
            next_question = question_num + 1
            if next_question <= 60:
                await asyncio.sleep(1.5)  # Небольшая пауза перед следующим вопросом
                await state.update_data(current_question=next_question)
                await show_question(callback, next_question, mode, state)
            else:
                # Все вопросы пройдены
                await asyncio.sleep(1.5)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")]
                ])
                await callback.message.edit_text(
                    "🎉 Поздравляем! Вы прошли все 60 вопросов!\n\n"
                    "Хотите начать заново?",
                    reply_markup=keyboard
                )
        else:
            # Неправильный ответ - показываем правильный ответ с кнопками
            # Используем полный текст правильного ответа без обрезания
            response_text = f"❌ Ошибочка!\n\n<b>Правильный ответ:</b>\n\n{correct_answer}"
            
            next_question = question_num + 1
            buttons = []
            
            if next_question <= 60:
                buttons.append([InlineKeyboardButton(
                    text="➡️ Следующий вопрос", 
                    callback_data=f"next_question_{next_question}_continuous"
                )])
            
            buttons.append([InlineKeyboardButton(
                text="🔙 Вернуться в меню", 
                callback_data="back_to_menu"
            )])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            # Если сообщение слишком длинное, разбиваем на части
            # Лимит Telegram - 4096 символов, но оставляем запас для форматирования
            max_length = 4000
            if len(response_text) > max_length:
                # Разбиваем на части
                part1 = response_text[:max_length]
                part2 = response_text[max_length:]
                await callback.message.edit_text(
                    part1,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                # Отправляем вторую часть как новое сообщение
                await callback.message.answer(
                    part2,
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    response_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
    else:
        # Режим выбора вопроса
        if is_correct:
            response_text = "✅ Молодец! Правильный ответ!"
        else:
            # Используем полный текст правильного ответа без обрезания
            response_text = f"❌ Ошибочка!\n\n<b>Правильный ответ:</b>\n\n{correct_answer}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Выбрать другой вопрос", callback_data="mode_select")],
            [InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")]
        ])
        
        # Если сообщение слишком длинное, разбиваем на части
        max_length = 4000
        if len(response_text) > max_length:
            # Разбиваем на части
            part1 = response_text[:max_length]
            part2 = response_text[max_length:]
            await callback.message.edit_text(
                part1,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            # Отправляем вторую часть как новое сообщение
            await callback.message.answer(
                part2,
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                response_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

@dp.callback_query(F.data.startswith("next_question_"))
async def handle_next_question(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Следующий вопрос' после неправильного ответа"""
    parts = callback.data.split("_")
    next_question = int(parts[2])
    mode = parts[3]
    
    await state.update_data(current_question=next_question)
    await show_question(callback, next_question, mode, state)
    await callback.answer()

async def main():
    """Главная функция запуска бота"""
    print("Бот запущен...")
    print(f"Загружено вопросов: {len(questions_data)}")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())

