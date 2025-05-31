# app.py
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from dotenv import load_dotenv
import requests
from models import db, Book, Category 

load_dotenv()

app = Flask(__name__)

# --- App Configuration and Database ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# --- Application Views (Routes) ---
@app.route('/')
def home():
    status_filter = request.args.get('status_filter')

    if status_filter in ['0', '1', '2']:
        books = Book.query.filter_by(status=int(status_filter)).all()
    else:
        books = Book.query.all()

    return render_template('home.html', books=books, status_filter=status_filter)


@app.route('/add_book', methods=['GET', 'POST'])
def add_book():
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        category_id = request.form.get('category_id') # Can be None
        
        new_book = Book(title=title, author=author)
        if category_id:
            new_book.category_id = category_id
        
        db.session.add(new_book)
        db.session.commit()
        flash('Book added successfully!', 'success')
        return redirect(url_for('home'))
    
    categories = Category.query.all()
    return render_template('add_book.html', categories=categories)

# --- Search Books with default popular results ---
@app.route('/search', methods=['GET', 'POST'])
def search_books():
    query = request.args.get('query', '').strip() # Get query, default to empty string, strip whitespace
    books_from_api = []
    
    # Base URL for Google Books API
    base_api_url = "https://www.googleapis.com/books/v1/volumes?"
    
    if query:
        # If a query is provided, search specifically for it
        api_url = f"{base_api_url}q={query}&printType=books&maxResults=20"
        title_text = f"Search results for '{query}'"
    else:
        # If no query, show some popular/random books
        # 'q=bestsellers' or 'q=fiction' are good general terms
        # For a more "random" feel, you could use a few different default queries
        api_url = f"{base_api_url}q=bestsellers&printType=books&maxResults=20" 
        title_text = "Browse Popular Books"
    
    try:
        response = requests.get(api_url)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        
        if 'items' in data:
            for item in data['items']:
                volume_info = item.get('volumeInfo', {})
                
                title = volume_info.get('title', 'No Title')
                authors = volume_info.get('authors', ['No Author'])
                author = ', '.join(authors)
                
                description = volume_info.get('description', 'No description available.')
                published_date = volume_info.get('publishedDate', 'No Date')
                page_count = volume_info.get('pageCount')
                
                image_links = volume_info.get('imageLinks', {})
                thumbnail = image_links.get('thumbnail') or image_links.get('smallThumbnail')
                
                isbn_13 = None
                industry_identifiers = volume_info.get('industryIdentifiers', [])
                for identifier in industry_identifiers:
                    if identifier.get('type') == 'ISBN_13':
                        isbn_13 = identifier.get('identifier')
                        break

                books_from_api.append({
                    'title': title,
                    'author': author,
                    'description': description,
                    'published_date': published_date,
                    'page_count': page_count,
                    'thumbnail': thumbnail,
                    'isbn': isbn_13,
                    'google_books_id': item.get('id')
                })
        else:
            if query: # Only flash if user actually searched and found nothing
                flash("No books found for your query.", 'info')
            else: # For default browse, just display empty results
                flash("Could not fetch popular books. Try searching!", 'info')

    except requests.exceptions.RequestException as e:
        flash(f"An error occurred while communicating with the API: {e}", 'danger')
    except ValueError: # JSON decoding error
        flash("Error parsing data from API. Please try again.", 'danger')
    
    return render_template('search_results.html', books=books_from_api, query=query, title_text=title_text)

# --- Add Book from API to Collection ---
@app.route('/add_from_api', methods=['POST'])
def add_from_api():
    title = request.form['title']
    author = request.form['author']
    isbn = request.form.get('isbn')
    description = request.form.get('description')
    year_published_str = request.form.get('published_date')
    page_count_str = request.form.get('page_count')
    cover_url = request.form.get('cover_url')

    year_published = None
    if year_published_str:
        try:
            year_published = int(year_published_str[:4])
        except (ValueError, TypeError):
            pass
    
    page_count = None
    if page_count_str:
        try:
            page_count = int(page_count_str)
        except (ValueError, TypeError):
            pass

    try:
        existing_book = None
        if isbn:
            existing_book = Book.query.filter_by(isbn=isbn).first()

        if existing_book:
            flash(f'Book "{title}" (ISBN: {isbn}) is already in your collection!', 'info')
        else:
            new_book = Book(
                title=title,
                author=author,
                isbn=isbn,
                description=description,
                year_published=year_published,
                page_count=page_count,
                cover_url=cover_url,
                status=0 # Default to "To Read"
            )
            db.session.add(new_book)
            db.session.commit()
            flash(f'Book "{title}" has been added to your collection!', 'success')
    except Exception as e:
        flash(f"An error occurred while adding the book: {e}", 'danger')

    return redirect(url_for('home'))

# --- Delete Book Route ---
@app.route('/remove_book/<int:book_id>', methods=['POST'])
def remove_book(book_id):
    book_to_delete = Book.query.get_or_404(book_id)
    try:
        db.session.delete(book_to_delete)
        db.session.commit()
        flash(f'Book "{book_to_delete.title}" removed from your shelf.', 'success')
    except Exception as e:
        db.session.rollback() # Rollback in case of an error
        flash(f"Error removing book: {e}", 'danger')
    return redirect(url_for('home'))



# --- Edit Book Route ---
@app.route('/edit_book/<int:book_id>', methods=['GET', 'POST'])
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    categories = Category.query.all()

    if request.method == 'POST':
        try:
            # ONLY update category, status, and current_page
            
            # Handle category
            category_id = request.form.get('category_id')
            book.category_id = int(category_id) if category_id else None

            # Handle status
            new_status = int(request.form.get('status'))
            book.status = new_status

            # Handle current_page based on new_status
            if new_status == 1: # If status is "Reading"
                current_page_str = request.form.get('current_page')
                book.current_page = int(current_page_str) if current_page_str else 0
            else: # If status is not "Reading", reset current_page
                book.current_page = None

            db.session.commit()
            flash(f'Book "{book.title}" updated successfully!', 'success')
            return redirect(url_for('home'))
        except ValueError:
            db.session.rollback()
            flash("Invalid input for current page. Please enter a valid number.", 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred while updating the book: {e}", 'danger')
    
    # For GET request, render the form with existing book data
    return render_template('edit_book.html', book=book, categories=categories)



if __name__ == '__main__':
    app.run(debug=True)