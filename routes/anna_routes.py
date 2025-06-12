# routes/anna_routes.py

from flask import Blueprint, request, redirect, url_for, flash
from flask_login import login_required, current_user
from services.annas_archive_service import try_add_original_or_alternatives

annas_archive_bp = Blueprint('annas_archive', __name__)


@annas_archive_bp.route('/add_from_annas_archive', methods=['POST'])
@login_required
def add_from_annas_archive():
    book_md5 = request.form.get('md5')
    book_title = request.form.get('title')
    book_author = request.form.get('author')
    book_year = request.form.get('year')
    book_cover = request.form.get('cover_url')

    # <<< KLUCZOWA POPRAWKA TUTAJ >>>
    # Upewniamy się, że odczytujemy pole 'file_format' z formularza.
    # To jest format klikniętej książki (np. 'epub' lub 'pdf').
    book_format = request.form.get('file_format', 'pdf')

    book_query = request.form.get('original_query',
                                  '')  # Prawdopodobnie tu jest literówka w Twoim kodzie, powinno być 'query'
    # Sprawdźmy w search_results.html, jak nazywa się pole z zapytaniem.
    # Jest tam: <input type="hidden" name="query" value="{{ query or '' }}">
    # Więc powinno być:
    book_query = request.form.get('query', '')

    # main logic in services
    message, category, _ = try_add_original_or_alternatives(
        book_title,
        book_author,
        book_year,
        book_cover,
        book_md5,
        book_format,
        book_query,
        current_user
    )
    flash(message, category)
    return redirect(url_for('home.home'))