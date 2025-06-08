# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

# placeholder, real object initialized in app.py
db = SQLAlchemy()


# BOOKS (MAIN)
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255), nullable=False)
    isbn = db.Column(db.String(20), unique=True, nullable=True)
    year_published = db.Column(db.Integer, nullable=True)
    publisher = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    page_count = db.Column(db.Integer, nullable=True)
    cover_url = db.Column(db.String(500), nullable=True)

    # Anna's Archive fields
    md5 = db.Column(db.String(32), unique=True, nullable=True)
    pdf_path = db.Column(db.String(500), nullable=True)
    file_format = db.Column(db.String(10), nullable=True)

    # Relations
    user_books = db.relationship('UserBook', backref='book', lazy=True, cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='book', lazy=True, cascade='all, delete-orphan')

    def average_rating(self):
        if not self.reviews:
            return None
        total = sum(review.rating for review in self.reviews if review.rating)
        count = len([review for review in self.reviews if review.rating])
        return round(total / count, 1) if count > 0 else None

    def user_has_review(self, user_id):
        return Review.query.filter_by(book_id=self.id, user_id=user_id).first() is not None

    def get_user_book(self, user_id):
        return UserBook.query.filter_by(book_id=self.id, user_id=user_id).first()

    def is_in_user_collection(self, user_id):
        return UserBook.query.filter_by(book_id=self.id, user_id=user_id).first() is not None

    def __repr__(self):
        return f"Book('{self.title}', '{self.author}')"


# USER BOOKS
class UserBook(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # Relations
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)

    # Personal reading data
    status = db.Column(db.Integer, default=0, nullable=False)  # 0=To Read, 1=Reading, 2=Read
    current_page = db.Column(db.Integer, default=0, nullable=True)
    personal_rating = db.Column(db.Integer, nullable=True)  # Personal rating 1-10
    personal_notes = db.Column(db.Text, nullable=True)  # Personal notes
    is_favorite = db.Column(db.Boolean, default=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Constraint: jeden użytkownik może mieć książkę tylko raz w kolekcji
    __table_args__ = (db.UniqueConstraint('user_id', 'book_id', name='unique_user_book'),)

    # Relations
    category = db.relationship('Category', backref='user_books')

    def __repr__(self):
        return f"UserBook(User: {self.user_id}, Book: {self.book_id}, Status: {self.status})"


# CATEGORY
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f"Category('{self.name}')"


# REVEIW
class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rating = db.Column(db.Integer, nullable=True)  # Community rating 1-5
    comment = db.Column(db.Text, nullable=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    date_modified = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)

    # Constraint: jeden użytkownik może dodać tylko jedną recenzję na książkę
    __table_args__ = (db.UniqueConstraint('user_id', 'book_id', name='unique_user_book_review'),)

    def __repr__(self):
        return f"Review('{self.rating}', User: {self.user_id}, Book: {self.book_id})"


# UŻYTKOWNICY
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    # Relations
    user_books = db.relationship('UserBook', backref='user', lazy=True, cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='author', lazy=True, cascade='all, delete-orphan')

    def get_books(self, status=None, favorite_only=False):
        query = UserBook.query.filter_by(user_id=self.id)

        if status is not None:
            query = query.filter_by(status=status)

        if favorite_only:
            query = query.filter_by(is_favorite=True)

        return query.all()

    def has_book(self, book_id):
        return UserBook.query.filter_by(user_id=self.id, book_id=book_id).first() is not None

    def add_book_to_collection(self, book_id, status=0):
        if not self.has_book(book_id):
            user_book = UserBook(user_id=self.id, book_id=book_id, status=status)
            db.session.add(user_book)
            return user_book
        return None

    def get_collection_stats(self):
        total = UserBook.query.filter_by(user_id=self.id).count()
        to_read = UserBook.query.filter_by(user_id=self.id, status=0).count()
        reading = UserBook.query.filter_by(user_id=self.id, status=1).count()
        read = UserBook.query.filter_by(user_id=self.id, status=2).count()
        favorites = UserBook.query.filter_by(user_id=self.id, is_favorite=True).count()

        return {
            'total': total,
            'to_read': to_read,
            'reading': reading,
            'read': read,
            'favorites': favorites
        }

    def __repr__(self):
        return f"User('{self.username}')"