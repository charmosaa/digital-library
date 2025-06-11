from flask import Blueprint, render_template, request, redirect, url_for
from flask import render_template, request, redirect, url_for, flash
from models import db, Book, Category, UserBook
from flask_login import login_required, current_user


home_bp = Blueprint('home', __name__)

@home_bp.route('/')
def home():
    status_filter = request.args.get('status_filter')
    only_favorites = request.args.get('only_favorites') == '1'
    sort_by = request.args.get('sort_by')
    category_filter = request.args.get('category_filter')

    if current_user.is_authenticated:
        # Pobierz UserBook dla zalogowanego użytkownika
        query = UserBook.query.filter_by(user_id=current_user.id).join(Book)
    else:
        # Dla niezalogowanych - pokaż dostępne książki do dodania do kolekcji
        return redirect(url_for('book.browse_books'))

    if status_filter in ['0', '1', '2']:
        query = query.filter(UserBook.status == int(status_filter))

    if only_favorites:
        query = query.filter(UserBook.is_favorite == True)

    if category_filter and category_filter.isdigit():
        query = query.filter(UserBook.category_id == int(category_filter))
    
    if sort_by == 'title_asc':
        query = query.order_by(Book.title.asc())
    elif sort_by == 'title_desc':
        query = query.order_by(Book.title.desc())
    elif sort_by == 'year_desc':
        query = query.order_by(Book.year_published.desc().nullslast())
    elif sort_by == 'year_asc':
        query = query.order_by(Book.year_published.asc().nullslast())
    else:
        query = query.order_by(UserBook.date_added.desc())

    user_books = query.all()
    categories = Category.query.order_by(Category.name).all() 

    # Statystyki
    stats = current_user.get_collection_stats()

    return render_template(
        'home.html',
        user_books=user_books,
        status_filter=status_filter,
        only_favorites=only_favorites,
        total_books=stats['total'],
        to_read_count=stats['to_read'],
        reading_count=stats['reading'],
        read_count=stats['read'],
        sort_by=sort_by,
        categories=categories,
        category_filter=category_filter
    )

@home_bp.route('/toggle_favorite/<int:book_id>', methods=['POST'])
@login_required
def toggle_favorite(book_id):
    user_book = UserBook.query.filter_by(user_id=current_user.id, book_id=book_id).first()

    if not user_book:
        flash("You don't have this book in your collection!", 'danger')
        return redirect(url_for('book.book_detail', book_id=book_id))

    user_book.is_favorite = not user_book.is_favorite

    try:
        db.session.commit()
        status = "added to" if user_book.is_favorite else "removed from"
        flash(f'Book "{user_book.book.title}" {status} favorites.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating favorite status: {e}", 'danger')

    previous_url = request.referrer or url_for('home.home')
    return redirect(previous_url)