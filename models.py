# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

# placeholder, real object initialized in app.py 
db = SQLAlchemy()


# BOOK model
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255), nullable=False)
    isbn = db.Column(db.String(20), unique=True, nullable=True) # should be unique
    year_published = db.Column(db.Integer, nullable=True)
    publisher = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    page_count = db.Column(db.Integer, nullable=True)
    cover_url = db.Column(db.String(500), nullable=True) # cover img link
    # Read status: 0 - To do, 1 - During, 2 - Finished
    status = db.Column(db.Integer, default=0, nullable=False)
    current_page = db.Column(db.Integer, default=0, nullable=True)
    rating = db.Column(db.Integer, nullable=True) # rating (from 1 - 5)
    review = db.Column(db.Text, nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_favorite = db.Column(db.Boolean, default=False)

    # relation to Category
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    category = db.relationship('Category', backref='books')

    def __repr__(self):
        return f"Book('{self.title}', '{self.author}', '{self.status}')"

# CATEGORY model
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f"Category('{self.name}')"