from flask import Blueprint, render_template, request, redirect, url_for
from flask import render_template, request, redirect, url_for, flash, send_file
from models import db, Book, Category, UserBook
from flask_login import login_required, current_user
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
import base64


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

from datetime import datetime, timedelta
from collections import Counter

@home_bp.route('/stats')
@login_required
def stats():
    user_books = UserBook.query.filter_by(user_id=current_user.id).all()

    stats = {
        'total': len(user_books),
        'read': sum(1 for b in user_books if b.status == 2),
        'reading': sum(1 for b in user_books if b.status == 1),
        'to_read': sum(1 for b in user_books if b.status == 0),
        'favorites': sum(1 for b in user_books if b.is_favorite),
        'total_pages': sum((b.current_page or 0) for b in user_books if b.status == 1)
    }

    # Daystreak: ile ostatnich dni z rzędu użytkownik coś przeczytał
    read_dates = [b.date_modified.date() for b in user_books if b.status == 2 and b.date_modified]
    unique_dates = sorted(set(read_dates), reverse=True)

    daystreak = 0
    today = datetime.utcnow().date()

    for i, date in enumerate(unique_dates):
        if date == today - timedelta(days=i):
            daystreak += 1
        else:
            break

    # Najczęściej wybierana kategoria
    category_names = [b.category.name for b in user_books if b.category]
    category_counter = Counter(category_names)
    top_category = category_counter.most_common(1)[0][0] if category_counter else "None"

    chart = None
    if category_counter:
        fig, ax = plt.subplots()

        # color pallete
        colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#c2c2f0', '#ffb3e6']

        ax.pie(
            category_counter.values(),
            labels=category_counter.keys(),
            autopct='%1.1f%%',
            startangle=140,
            colors=colors[:len(category_counter)]  # trim or match number of categories
        )
        ax.set_title("Your Book Categories")

        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        chart = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        plt.close()

    return render_template('stats.html',
                           stats=stats,
                           daystreak=daystreak,
                           top_category=top_category, 
                           chart=chart)


@home_bp.route('/stats/chart.png')
@login_required
def stats_chart():
    user_books = UserBook.query.filter_by(user_id=current_user.id).all()

    labels = ['Read', 'Reading', 'To Read', 'Favorites']
    values = [
        sum(1 for b in user_books if b.status == 2),
        sum(1 for b in user_books if b.status == 1),
        sum(1 for b in user_books if b.status == 0),
        sum(1 for b in user_books if b.is_favorite),
    ]

    fig, ax = plt.subplots()
    ax.bar(labels, values, color=['green', 'gold', 'cyan', 'red'])
    ax.set_title('Reading Breakdown')

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    return send_file(buf, mimetype='image/png')
