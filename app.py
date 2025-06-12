import os
from flask import Flask
from dotenv import load_dotenv
from models import db, Category, User
from flask_migrate import Migrate
from flask_login import LoginManager
from scripts.load_categories import load_categories_from_file
from routes.assistant_routes import assistant_bp
from routes.anna_routes import annas_archive_bp
from routes.auth_routes import auth_bp 
from routes.book_routes import book_bp
from routes.home_routes import home_bp
from routes.review_routes import review_bp
from routes.search_routes import search_bp
from flask_misaka import Misaka
load_dotenv()

app = Flask(__name__)
Misaka(app)

app = Flask(__name__)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- App Configuration and Database ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'  # database will be in instance/site.db
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['RAPIDAPI_KEY'] = os.getenv('RAPIDAPI_KEY')

# for uploaded PDFs
PDF_FOLDER = os.path.join(app.instance_path, 'pdfs')
os.makedirs(PDF_FOLDER, exist_ok=True)

db.init_app(app)
migrate = Migrate(app, db)

from sqlalchemy import inspect

with app.app_context():
    inspector = inspect(db.engine)
    if 'category' in inspector.get_table_names():
        if Category.query.first() is None:
            print("Loading categories from file...")
            categories_file = os.path.join(os.path.dirname(__file__), 'data', 'categories.json')
            load_categories_from_file(categories_file)
            print("Categories loaded.")
        else:
            print("Categories already loaded.")



# --- USER AUTHENTICATION ROUTES ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ROUTES (BLUEPRINTSs)
app.register_blueprint(home_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(book_bp)
app.register_blueprint(search_bp)
app.register_blueprint(review_bp)
app.register_blueprint(annas_archive_bp)
app.register_blueprint(assistant_bp)


if __name__ == '__main__':
    app.run(debug=True)
