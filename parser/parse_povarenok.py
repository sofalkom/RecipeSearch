import argparse
import bs4
from datetime import datetime
from functools import reduce
import math
from multiprocessing import Pool
import pandas as pd
from pathlib import Path
import requests
from tqdm import tqdm

from const import n_workers


def get_soup(url):
    req = requests.get(url)
    return bs4.BeautifulSoup(req.text, 'lxml')


def get_recipe_urls_from_page(url):
    soup = get_soup(url)
    content_div = soup.find('div', 'content-md')
    pages_url = [recipe_preview.find('h2').find('a')['href']
                 for recipe_preview in content_div.find_all('article', 'item-bl')]
    return pages_url


def get_recipe_from_page(url):
    soup = get_soup(url)
    try:
        recipe_name = soup.find('h1').get_text().strip()
    except Exception as e:
        return [{'url': url, 'name': None, 'calories' : None}]
    if recipe_name == 'Страница не найдена':
        return [{'url': url, 'name': recipe_name, 'calories' : None}]

    ingredients_tags = soup.find_all(attrs={"itemprop" : "recipeIngredient"})
    try:
        calories_el = soup.find(attrs={"itemprop" : "calories"})
        calories = float(calories_el.get_text(strip=True).split()[0])
    except Exception as e:
        calories = None
    
    protein_info = soup.find(itemprop="proteinContent")
    protein_count = None
  
    if protein_info:
        protein_count = float(protein_info.get_text(strip=True).split(" ")[0])
    
    fat_info = soup.find(itemprop="fatContent")
    fat_count = None
    if fat_info:
        fat_count = float(fat_info.get_text(strip=True).split(" ")[0])
        
    carbohydrate_info = soup.find(itemprop="carbohydrateContent")
    carbohydrate_count = None
  
    if carbohydrate_info:
        carbohydrate_count = float(carbohydrate_info.get_text(strip=True).split(" ")[0])
    
        
    views_span = soup.find('span', class_='i-views')

    views_count = None
    if views_span:
        views_count = int(views_span.get_text(strip=True))
    else:
        print("No <span> with class 'i-views' found.")
    return [{'url': url, 'name': recipe_name, 'calories' : calories, 
             'protein' : protein_count, 'fat' : fat_count, 'carbohydrate' : carbohydrate_count, 'views' : views_count}]


def get_pages_range():
    main_url = 'https://www.povarenok.ru/recipes/~1/'
    soup = get_soup(main_url)

    recipe_count_div = soup.find('div', 'bl-right')
    recipe_count = int(recipe_count_div.find('strong').get_text())
    recipe_per_page_count = 15
    pages_count = math.ceil(recipe_count / recipe_per_page_count)

    pages_range = [f'https://www.povarenok.ru/recipes/~{i}/' for i in range(1, pages_count + 1)]
    return pages_range


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Parser of recipes from povarenok.ru site')
    parser.add_argument(
        '--save_path',
        help='path for saving data',
        type=Path,
        required=True
    )
    args = parser.parse_args()
    print(f'Run with arguments: {args}')

    pages_range = get_pages_range()

    print("Let's find all recipe urls")
    with Pool(n_workers) as p:
        p = Pool(n_workers)
        maped_recipe_urls = tqdm(p.imap_unordered(get_recipe_urls_from_page, pages_range), total=len(pages_range))
        recipe_urls = reduce(lambda x, y: x + y, maped_recipe_urls)
        recipe_urls = set(recipe_urls)

    print("Let's parse all recipe urls")
    with Pool(n_workers) as p:
        maped_recipes = tqdm(p.imap_unordered(get_recipe_from_page, recipe_urls), total=len(recipe_urls))
        recipes_data = pd.DataFrame(reduce(lambda x, y: x + y, maped_recipes))

    current_datetime = datetime.today().strftime('%Y_%m_%d')
    recipes_data.to_csv(args.save_path / f'povarenok_recipes_{current_datetime}.csv', index=False)

    print("Well done")
