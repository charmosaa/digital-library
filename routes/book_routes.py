from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import current_user
from flask import render_template, request, redirect, url_for, flash, current_app, send_file
from models import db, Book, Category, UserBook
import os
from flask_login import login_required, current_user


book_bp = Blueprint('book', __name__)

@book_bp.route('/browse_books')
def browse_books():
    """Przeglądaj wszystkie dostępne książki w systemie"""
    query = request.args.get('query', '').strip()

    books_query = Book.query

    if query:
        books_query = books_query.filter(
            Book.title.contains(query) | Book.author.contains(query)
        )

    books = books_query.order_by(Book.title).all()

    # Dla zalogowanych użytkowników - sprawdź które książki już mają
    user_book_ids = []
    if current_user.is_authenticated:
        user_book_ids = [ub.book_id for ub in UserBook.query.filter_by(user_id=current_user.id).all()]

    return render_template('browse_books.html', books=books, user_book_ids=user_book_ids, query=query)


@book_bp.route('/add_book_to_collection/<int:book_id>', methods=['POST'])
@login_required
def add_book_to_collection(book_id):
    """Dodaj istniejącą książkę do kolekcji użytkownika"""
    book = Book.query.get_or_404(book_id)

    # Sprawdź czy użytkownik już ma tę książkę
    existing = UserBook.query.filter_by(user_id=current_user.id, book_id=book_id).first()
    if existing:
        flash(f"You already have '{book.title}' in your collection!", 'info')
        return redirect(url_for('book.book_detail', book_id=book_id))

    # Dodaj książkę do kolekcji
    user_book = UserBook(
        user_id=current_user.id,
        book_id=book_id,
        status=0,  # Do przeczytania
        is_favorite=False
    )

    try:
        db.session.add(user_book)
        db.session.commit()
        flash(f"'{book.title}' added to your collection!", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding book to collection: {e}", 'danger')

    return redirect(url_for('book.book_detail', book_id=book_id))

# --- Route to serve/read PDF files ---
@book_bp.route('/read_book/<int:book_id>')
@login_required
def read_book(book_id):
    book = Book.query.get_or_404(book_id)

    # Sprawdź czy użytkownik ma tę książkę w kolekcji
    user_book = UserBook.query.filter_by(user_id=current_user.id, book_id=book_id).first()
    if not user_book:
        flash("You don't have this book in your collection!", 'danger')
        return redirect(url_for('book.book_detail', book_id=book_id))

    if book.pdf_path and os.path.exists(book.pdf_path):
        try:
            return send_file(book.pdf_path, as_attachment=False)
        except Exception as e:
            current_app.logger.error(f"Error sending file {book.pdf_path}: {e}")
            flash("Could not open the book file.", "danger")
            return redirect(url_for('book.book_detail', book_id=book_id))
    else:
        flash("PDF file not found for this book.", "danger")
        return redirect(url_for('book.book_detail', book_id=book_id))


# --- Delete Book Route (usuwa z kolekcji użytkownika) ---
@book_bp.route('/remove_book/<int:book_id>', methods=['POST'])
@login_required
def remove_book(book_id):
    """Usuń książkę z kolekcji użytkownika (nie usuwa głównej książki)"""
    user_book = UserBook.query.filter_by(user_id=current_user.id, book_id=book_id).first()

    if not user_book:
        flash("You don't have this book in your collection!", 'danger')
        return redirect(url_for('home.home'))

    book_title = user_book.book.title

    try:
        db.session.delete(user_book)
        db.session.commit()
        flash(f'Book "{book_title}" removed from your collection.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error removing book: {e}", 'danger')

    return redirect(url_for('home.home'))

@book_bp.route('/edit_book/<int:book_id>', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    user_book = UserBook.query.filter_by(user_id=current_user.id, book_id=book_id).first()

    if not user_book:
        flash("You don't have this book in your collection!", 'danger')
        return redirect(url_for('book.book_detail', book_id=book_id))

    categories = Category.query.all()

    if request.method == 'POST':
        try:
            category_id = request.form.get('category_id')
            user_book.category_id = int(category_id) if category_id else None

            new_status = int(request.form.get('status'))
            user_book.status = new_status

            if new_status == 1:  # Reading
                current_page_str = request.form.get('current_page')
                user_book.current_page = int(current_page_str) if current_page_str and current_page_str.isdigit() else 1
                if book.page_count and user_book.current_page > book.page_count:
                    user_book.current_page = book.page_count
            elif new_status == 2:  # Read
                user_book.current_page = book.page_count if book.page_count else 0
            else:  # To Read
                user_book.current_page = 0

            db.session.commit()
            flash(f'Book "{book.title}" updated successfully!', 'success')
            return redirect(url_for('home.home'))
        except ValueError:
            db.session.rollback()
            flash("Invalid input for current page. Please enter a valid number.", 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred while updating the book: {e}", 'danger')

    return render_template('edit_book.html', book=book, user_book=user_book, categories=categories)

@book_bp.route('/book/<int:book_id>')
def book_detail(book_id):
    book = Book.query.get_or_404(book_id)

    user_book = None
    if current_user.is_authenticated:
        user_book = UserBook.query.filter_by(user_id=current_user.id, book_id=book_id).first()

    return render_template('book_detail.html', book=book, user_book=user_book)
