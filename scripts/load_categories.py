import json
from app import db
from models import Category

def load_categories_from_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as file:
        categories = json.load(file)

    for name in categories:
        if not Category.query.filter_by(name=name).first():
            category = Category(name=name)
            db.session.add(category)

    db.session.commit()
    print("Categories uploaded succesfully")
