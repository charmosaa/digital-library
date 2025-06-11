from flask import Blueprint, request, redirect, url_for
from flask_login import current_user
from flask import Blueprint, request, redirect, url_for, flash
from models import db, Book, Review
from flask_login import login_required, current_user

from datetime import datetime


review_bp = Blueprint('review', __name__)

# --- REVIEW ROUTES ---
@review_bp.route('/book/<int:book_id>/add_review', methods=['POST'])
@login_required
def add_review(book_id):
    """Dodawanie nowej recenzji"""
    book = Book.query.get_or_404(book_id)

    # Sprawdź czy użytkownik już ma recenzję dla tej książki
    existing_review = Review.query.filter_by(book_id=book_id, user_id=current_user.id).first()
    if existing_review:
        flash("You already have a review for this book. You can edit it instead.", 'warning')
        return redirect(url_for('book.book_detail', book_id=book_id))

    try:
        rating = request.form.get('rating')
        comment = request.form.get('comment', '').strip()

        # Walidacja
        if not rating and not comment:
            flash("Please provide either a rating or a comment.", 'warning')
            return redirect(url_for('book.book_detail', book_id=book_id))

        if rating and (not rating.isdigit() or int(rating) < 1 or int(rating) > 5):
            flash("Rating must be between 1 and 5.", 'danger')
            return redirect(url_for('book.book_detail', book_id=book_id))

        # Tworzenie nowej recenzji
        new_review = Review(
            rating=int(rating) if rating else None,
            comment=comment if comment else None,
            user_id=current_user.id,
            book_id=book_id
        )

        db.session.add(new_review)
        db.session.commit()

        flash("Your review has been added successfully!", 'success')

    except Exception as e:
        db.session.rollback()
        flash(f"Error adding review: {e}", 'danger')

    return redirect(url_for('book.book_detail', book_id=book_id))


@review_bp.route('/book/<int:book_id>/edit_review/<int:review_id>', methods=['POST'])
@login_required
def edit_review(book_id, review_id):
    """Edytowanie istniejącej recenzji"""
    review = Review.query.get_or_404(review_id)

    # Sprawdź czy recenzja należy do aktualnego użytkownika
    if review.user_id != current_user.id:
        flash("You can only edit your own reviews.", 'danger')
        return redirect(url_for('book.book_detail', book_id=book_id))

    try:
        rating = request.form.get('rating')
        comment = request.form.get('comment', '').strip()

        # Walidacja
        if not rating and not comment:
            flash("Please provide either a rating or a comment.", 'warning')
            return redirect(url_for('book.book_detail', book_id=book_id))

        if rating and (not rating.isdigit() or int(rating) < 1 or int(rating) > 5):
            flash("Rating must be between 1 and 5.", 'danger')
            return redirect(url_for('book.book_detail', book_id=book_id))

        # Aktualizacja recenzji
        review.rating = int(rating) if rating else None
        review.comment = comment if comment else None
        review.date_modified = datetime.utcnow()

        db.session.commit()
        flash("Your review has been updated successfully!", 'success')

    except Exception as e:
        db.session.rollback()
        flash(f"Error updating review: {e}", 'danger')

    return redirect(url_for('book.book_detail', book_id=book_id))


@review_bp.route('/book/<int:book_id>/delete_review/<int:review_id>', methods=['POST'])
@login_required
def delete_review(book_id, review_id):
    """Usuwanie recenzji"""
    review = Review.query.get_or_404(review_id)

    # Sprawdź czy recenzja należy do aktualnego użytkownika
    if review.user_id != current_user.id:
        flash("You can only delete your own reviews.", 'danger')
        return redirect(url_for('book.book_detail', book_id=book_id))

    try:
        db.session.delete(review)
        db.session.commit()
        flash("Your review has been deleted.", 'info')

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting review: {e}", 'danger')

    return redirect(url_for('book.book_detail', book_id=book_id))

