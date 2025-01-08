# RecipeSearch
Репозиторий проекта по исследовательскому анализу данных и созданию телеграм бота для поиска рецептов

## Работа с данными

```EDA.ipynb``` -- сбор и предобработка данных, помещение датасета в локальную базу данных, проведение исследовательского анализа данных

Для сбора доп. данных под наши нужды был модифицирован парсер https://github.com/rogozinushka/povarenok_recipes_parser

## Телеграм бот для поиска рецептов

Для запуска бота нужно запустить скрипт из корня репозитория

```
python recipeBot.py --token your_bot_token
```
Также для работы бота необходимо разместить локальную базу данных *.db в корень репозитория.

В данный момент бот не работает круглосуточно, включается по запросу

Из соображений безопасности используемая база данных и токен бота не прилагаются
