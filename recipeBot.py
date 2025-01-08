import argparse
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

class UserStateManager:
    def __init__(self):
        self.states = {}

    def set_state(self, user_id, state):
        self.states[user_id] = state

    def get_state(self, user_id):
        return self.states[user_id]


def check_tables():
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print("Existing tables in database:")
        for table in tables:
            print(table[0])
        
    except Exception as e:
        print(f"Error checking tables: {e}")
    finally:
        conn.close()


def connect_db():
    return sqlite3.connect('database.db')


def add_favorite_recipe(user_id: int, url: str, recipe_name: str) -> bool:
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute('INSERT OR IGNORE INTO FAVORITE_RECIPES (user_id, url, name) VALUES (?, ?, ?)', 
                       (user_id, url, recipe_name))
        
        conn.commit()
        
        logger.info(f"Added favorite recipe '{recipe_name}' for user {user_id}.")
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Error adding favorite recipe '{recipe_name}' for user {user_id}: {e}")
        conn.close()
        return False


def preproc_query(word):
    res = word.replace("/suggest", " ")
    res = word.replace(",", " ")
    
    return res


def find_recipes(search_terms, user_id):
    try:
        conn = connect_db()
        cursor = conn.cursor()
        
        #Разобьём условия на слова
        terms = [preproc_query(word) for word in search_terms]
        words = [term.strip().lower() for term in ' '.join(terms).split()]
        
        ingredient_placeholders = ['ingredients LIKE ?'] * len(words)
        name_placeholders = ['name COLLATE NOCASE LIKE ?'] * len(words)
        
        #Шаблон запроса
        where_clause = ' OR '.join(ingredient_placeholders + name_placeholders)
        
        #Параметры поиска
        params = [f'%{word}%' for word in words] * 2
        
        query = f"""
        SELECT url, name, ingredients FROM RECIPES 
        WHERE {where_clause}
        """
        
        cursor.execute(query, params)
        matches = cursor.fetchall()

        cursor.execute("SELECT url FROM FAVORITE_RECIPES WHERE user_id = ?", (user_id,))
        favorite_urls = {row[0] for row in cursor.fetchall()}  # Use a set for faster lookup

        #Считаем совпадения
        recipe_scores = []
        
        for url, name, ingredients in matches:
            score = sum(1 for word in words if word in ingredients.lower() or word in name.lower())
            if url in favorite_urls:
                score *= 2  #Удваиваем счёт, если есть совпадения с избранным (персонализация поиска)
            recipe_scores.append((url, name, ingredients, score))
        
        #Сортируем рецепты по релевантности
        sorted_recipes = sorted(recipe_scores, key=lambda x: x[3], reverse=True)

        return sorted_recipes
    
    except Exception as e:
        logger.error(f"Error while finding recipes: {e}")
        return None  

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        # [InlineKeyboardButton("Start", callback_data='start')],
        [InlineKeyboardButton("Найти рецепты", callback_data='suggest')],
        [InlineKeyboardButton("Показать избранные рецепты", callback_data='show_favorites')],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text('Пожалуйста, выберите команду:', reply_markup=reply_markup)
    

async def suggest_recipes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        user_args = []
        if context.args is not None:
            user_args = context.args 
        user_input = ' '.join(user_args)
        
        if not user_input:
            await context.bot.send_message(chat_id=user_id, text='Пожалуйста, предоставьте ингредиенты или название рецепта в следующем формате:\n/suggest ингредиент1, ингредиент2, название')
            return
        
        search_terms = [term.strip().lower() for term in user_input.split(',')]
        
        recipes = find_recipes(search_terms, user_id)

        if recipes is None:
            await context.bot.send_message(chat_id=user_id, text='Произошла ошибка во время обработки запроса. Пожалуйста, попробуйте снова.')
            return

        if not recipes:
            await context.bot.send_message(chat_id=user_id, text='Подходящие рецепты не найдены.')
            return
        
        user_state_manager.set_state(user_id, {'recipes': recipes, 'page': 0})

        logger.info(f"User {user_id} requested recipes with search terms: {search_terms}.")
        
        await display_recipes(user_id, context)

    except Exception as e:
        logger.error(f"Error in suggest_recipes: {e}")
        await context.bot.send_message(chat_id=user_id, text='Произошла ошибка во время обработки команды. Пожалуйста, перепроверьте запрос и попробуйте снова.')


async def display_recipes(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = user_state_manager.get_state(user_id)

    if not state or 'recipes' not in state:
        await context.bot.send_message(chat_id=user_id, text='Рецепты не найдены. Пожалуйста, используйте /suggest снова.')
        return

    recipes = state['recipes']
    page = state['page']
    
    start_index = page * 5
    end_index = start_index + 5
    
    current_recipes = recipes[start_index:end_index]

    if not current_recipes:
        await context.bot.send_message(chat_id=user_id, text='Нет рецептов для отображения :(')
        return

    response = "Вот, что я нашёл:\n"
    keyboard = []

    for url, name, _, _ in current_recipes:
        response += f"{name}\n"
        keyboard.append([
            InlineKeyboardButton("В избранное", callback_data=f'favorite_{url}'),
            InlineKeyboardButton(name, url=url)
        ])

    navigation_buttons = []
    
    if start_index > 0:
        navigation_buttons.append(InlineKeyboardButton("Назад", callback_data='previous'))
    
    if end_index < len(recipes):
        navigation_buttons.append(InlineKeyboardButton("Далее", callback_data='next'))

    if navigation_buttons:
        keyboard.append(navigation_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(chat_id=user_id, text=response, reply_markup=reply_markup)
    
    logger.info(f"Displayed recipes to user {user_id}: {current_recipes}")


async def show_favorites(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT name, url FROM FAVORITE_RECIPES WHERE user_id = ?", (user_id,))
        favorites = cursor.fetchall()
        
        if not favorites:
            await context.bot.send_message(chat_id=user_id, text='У вас нет избранных рецептов.')
            return
        
        response = "Ваши избранные рецепты:\n"
        keyboard = []
        
        for recipe_name, url in favorites:
            response += f"{recipe_name}\n"
            keyboard.append([InlineKeyboardButton(recipe_name, url=url)])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(chat_id=user_id, text=response, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error retrieving favorites for user {user_id}: {e}")
        await context.bot.send_message(chat_id=user_id, text='Произошла ошибка во время получения ваших избранных рецептов.')
    
    finally:
        conn.close()


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Button handler invoked.")
    
    query = update.callback_query
    await query.answer()  

    user_id = query.from_user.id 
    
    if user_id not in user_state_manager.states:
        user_state_manager.set_state(user_id, {'recipes': None, 'page': 0})

    state = user_state_manager.get_state(user_id)

    if query.data == 'show_favorites':
        await show_favorites(user_id, context)
        return 

    if query.data == 'suggest':
        await suggest_recipes(update, context)
        return


    #Добавление рецепта в избранное
    if query.data.startswith('favorite_'):
        url = query.data.split('_', 1)[1]  
        recipe_name = next((name for url_, name, _, _ in state['recipes'] if url_ == url), None)

        if recipe_name:
            added = add_favorite_recipe(user_id, url, recipe_name)
            if added:
                await context.bot.send_message(chat_id=user_id, text=f'Рецепт "{recipe_name}" добавлен в избранное!')
            else:
                await context.bot.send_message(chat_id=user_id, text=f'Не удалось добавить рецепт :(')

    #Обновление страницы
    elif query.data == 'next':
        state['page'] += 1 
    elif query.data == 'previous':
        state['page'] -= 1 
    
    #Проверка выхода за пределы страниц
    if state['page'] < 0:
        state['page'] = 0
    
    logger.info(f"User {user_id} navigated to page {state['page']}.")
    
    await display_recipes(user_id, context)
    
    
def main():
    parser = argparse.ArgumentParser(
        description='Parser of recipes from povarenok.ru site')
    parser.add_argument(
        '--token',
        help="token for bot",
        required=True
    )
    args = parser.parse_args()
    print(f'Run with arguments: {args}')
    
    check_tables()
    global user_state_manager
    global logger
    
    # Set up logging here
    logging.basicConfig(
        filename='logs.txt',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        encoding='utf-8'
    )
    logger = logging.getLogger(__name__)
    user_state_manager =  UserStateManager()
    bot_token = args.token
    application = ApplicationBuilder().token(bot_token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("suggest", suggest_recipes))
    application.add_handler(CommandHandler("show_favorites", show_favorites))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.run_polling()

if __name__ == '__main__':
    main()
