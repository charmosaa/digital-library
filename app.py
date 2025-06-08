# app.py
import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, send_file, jsonify
from dotenv import load_dotenv
import requests
from models import db, Book, Category
from flask_migrate import Migrate
import re
import json
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import User
from werkzeug.security import generate_password_hash, check_password_hash
from flask import abort


load_dotenv()

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


# --- Helper function to sanitize filenames ---
def sanitize_filename(filename):
    # delete unallowed chars and shorten
    filename = re.sub(r'[^\w\s-]', '', filename).strip().lower()
    filename = re.sub(r'[-\s]+', '-', filename)
    return filename[:100]  # max 100 chars


# --- Application Views (Routes) ---
@app.route('/')
def home():
    status_filter = request.args.get('status_filter')
    only_favorites = request.args.get('only_favorites') == '1'
    sort_by = request.args.get('sort_by')

    if current_user.is_authenticated:
        query = Book.query.filter_by(user_id=current_user.id)
    else:
        query = Book.query.filter_by(user_id=None)  # just unlogged books

    if status_filter in ['0', '1', '2']:
        query = query.filter_by(status=int(status_filter))

    if only_favorites:
        query = query.filter_by(is_favorite=True)

    if sort_by == 'title_asc':
        query = query.order_by(Book.title.asc())
    elif sort_by == 'title_desc':
        query = query.order_by(Book.title.desc())
    elif sort_by == 'year_desc':
        query = query.order_by(Book.year_published.desc().nullslast())
    elif sort_by == 'year_asc':
        query = query.order_by(Book.year_published.asc().nullslast())
    elif sort_by == 'favorite':
        query = query.order_by(Book.is_favorite.desc(), Book.title.asc())
    else:
        query = query.order_by(Book.date_added.desc())

    books = query.all()

    total_books = query.count()
    to_read_count = query.filter_by(status=0).count()
    reading_count = query.filter_by(status=1).count()
    read_count = query.filter_by(status=2).count()

    return render_template(
        'home.html',
        books=books,
        status_filter=status_filter,
        only_favorites=only_favorites,
        total_books=total_books,
        to_read_count=to_read_count,
        reading_count=reading_count,
        read_count=read_count,
        sort_by=sort_by
    )



@app.route('/add_book', methods=['GET', 'POST'])
@login_required
def add_book():
    if not current_user.is_authenticated:
        if request.method == 'POST':
            return jsonify({'error': 'unauthenticated'}), 401
        else:
            return render_template('add_book.html', show_login_popup=True)


    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        category_id = request.form.get('category_id')  # Can be None

        new_book = Book(title=title, author=author, user_id=current_user.id)
        if category_id:
            new_book.category_id = int(category_id) if category_id else None  # has to be int

        db.session.add(new_book)
        db.session.commit()
        flash('Book added successfully!', 'success')
        return redirect(url_for('home'))

    categories = Category.query.all()
    return render_template('add_book.html', categories=categories)


@app.route('/search', methods=['GET'])
def search_books():
    query = request.args.get('query', '').strip()
    books_from_api = []
    title_text = "Search Results"

    if not query:
        flash("Please enter a search query.", "info")
        return render_template('search_results.html', books=[], query=query, title_text="Search for Books")

    if not app.config['RAPIDAPI_KEY']:
        flash("RapidAPI key is not configured. Please contact the administrator.", "danger")
        return render_template('search_results.html', books=[], query=query, title_text=title_text)

    url = "https://annas-archive-api.p.rapidapi.com/search"
    querystring = {
        "q": query
    }
    headers = {
        "X-RapidAPI-Key": app.config['RAPIDAPI_KEY'],
        "X-RapidAPI-Host": "annas-archive-api.p.rapidapi.com"
    }

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=30)
        print(f"Search API response status: {response.status_code}") # log status
        response.raise_for_status()
        data = response.json()
        #print(f"Search API response data: {json.dumps(data, indent=2)}") # whole JSON (for debug)

        # Check if the response is a dictionary and contains the 'books' key,
        # and whether the value under this key is a list.
        if isinstance(data, dict) and 'books' in data and isinstance(data['books'], list):
            print("API response is a dict with a 'books' list.")
            api_response_items = data['books']  # Assign the book list
        else:
            # This condition is now more precise for this API
            print(
                f"API response structure not recognized (expected dict with 'books' list) or 'books' list is empty. Data: {data}")
            # Flash message is already below if api_response_items remains empty

        for item in api_response_items:
            # Zmień warunek na sprawdzanie zarówno PDF jak i EPUB
            if item.get('format', '').lower() in ['pdf', 'epub']:
                books_from_api.append({
                    'title': item.get('title', 'No Title'),
                    'author': item.get('author', 'No Author'),
                    'year': item.get('year'),
                    'cover_url': item.get('imgUrl'),
                    'md5': item.get('md5'),
                    'file_format': item.get('format', '').lower()  # Zapisz format
                })


            title_text = f"Search results for '{query}' "

    except requests.exceptions.Timeout:
        flash("The request to Anna's Archive timed out. Please try again later.", 'danger')
    except requests.exceptions.HTTPError as e:
        flash_message = f"Error from Anna's Archive API: {e.response.status_code}."
        try:
            error_detail = e.response.json()  # Try to read JSON from error
            flash_message += f" Message: {error_detail.get('message', e.response.text)}"
        except ValueError:  # If error response is not JSON
            flash_message += f" Response: {e.response.text[:200]}"
        print(f"HTTPError in search_books: {flash_message}")
        flash(flash_message, 'danger')
    except requests.exceptions.RequestException as e:
        print(f"RequestException in search_books: {e}")
        flash(f"An error occurred while communicating with Anna's Archive: {e}", 'danger')
    except json.JSONDecodeError as e:  # Changed from ValueError to be more specific
        print(f"JSONDecodeError in search_books: {e}. Response text: {response.text[:500] if 'response' in locals() else 'N/A'}")
        flash("Error parsing data from Anna's Archive API. Please try again.", 'danger')
    except Exception as e:  # Generic fallback
        print(f"Unexpected error in search_books: {e}")
        flash(f"An unexpected error occurred during search: {e}", 'danger')

    return render_template('search_results.html', books=books_from_api, query=query, title_text=title_text)


def are_strings_similar(s1, s2):
    if not s1 or not s2: return False
    s1_clean = ''.join(filter(str.isalnum, s1)).lower()
    s2_clean = ''.join(filter(str.isalnum, s2)).lower()
    return s1_clean == s2_clean or s1_clean in s2_clean or s2_clean in s1_clean


@app.route('/add_from_annas_archive', methods=['POST'])
@login_required
def add_from_annas_archive():
    original_title = request.form['title']
    original_author = request.form['author']
    original_year_str = request.form.get('year')
    original_cover_url = request.form.get('cover_url')
    original_md5 = request.form.get('md5')
    original_file_format = request.form.get('file_format', 'pdf')
    original_search_query = request.form.get('original_search_query', original_title)

    if not original_md5:
        flash("MD5 hash is missing.", "danger")
        return redirect(request.referrer or url_for('search_books'))

    # Check if a book with this MD5 already exists
    existing_book_original_md5 = Book.query.filter_by(md5=original_md5).first()
    if existing_book_original_md5:
        flash(f'The book "{original_title}" (this specific version) is already in your shelf!', 'info')
        return redirect(url_for('home'))

    pdf_full_path_final = ""  # Path to the final downloaded file

    def attempt_download_and_add(book_md5, book_title, book_author, book_year_str, book_cover_url, book_file_format,
                                 is_alternative=False):
        nonlocal pdf_full_path_final
        # Check if THIS VERSION (MD5) already exists before downloading
        existing_version = Book.query.filter_by(md5=book_md5).first()
        if existing_version:
            if is_alternative:
                print(f"Alternative MD5 {book_md5} ('{book_title}') already exists in DB. Skipping download.")
                return False, "Alternative version already in collection."

        year_p = None
        if book_year_str and str(book_year_str).isdigit():
            year_p = int(book_year_str)

        get_links_url = "https://annas-archive-api.p.rapidapi.com/download"
        get_links_params = {"md5": book_md5}
        api_headers = {
            "X-RapidAPI-Key": app.config['RAPIDAPI_KEY'],
            "X-RapidAPI-Host": "annas-archive-api.p.rapidapi.com"
        }

        # Sanitize filename and use correct extension
        sanitized_title = sanitize_filename(book_title)
        file_extension = book_file_format.lower()
        current_fname = f"{sanitized_title}_{book_md5}.{file_extension}"
        current_full_path = os.path.join(PDF_FOLDER, current_fname)

        try:
            print(f"Attempting to get links for MD5: {book_md5} ('{book_title}')")
            links_resp = requests.get(get_links_url, headers=api_headers, params=get_links_params, timeout=30)
            print(f"Links response for {book_md5}: {links_resp.status_code}")

            if links_resp.status_code != 200:
                if book_md5 == original_md5:
                    try:
                        err_detail = links_resp.json()
                        api_err_msg = err_detail.get("message", links_resp.text)
                        if "member_download endpoint" in api_err_msg.lower():
                            print(f"Detected 'member_download endpoint' for original MD5 {book_md5}")
                            return "member_required", "Original book requires membership."
                    except (json.JSONDecodeError, ValueError):
                        pass
                links_resp.raise_for_status()

            dl_links = links_resp.json()
            if not dl_links or not isinstance(dl_links, list) or not dl_links[0]:
                return False, f"No download links for '{book_title}'."

            downloaded_successfully = False
            last_err_msg_dl = "All download links failed."
            for i, actual_link in enumerate(dl_links):
                print(
                    f"Attempting {file_extension.upper()} from link {i + 1}/{len(dl_links)}: {actual_link} for '{book_title}'")
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
                    with requests.get(actual_link, stream=True, timeout=180, headers=headers,
                                      allow_redirects=True) as r:
                        r.raise_for_status()

                        # Check file type based on content
                        content_type = r.headers.get('Content-Type', '').lower()
                        content_disposition = r.headers.get('Content-Disposition', '').lower()

                        # Read first 4 bytes to check magic number
                        first_bytes = next(r.iter_content(4), b'')
                        is_valid_file = False

                        if book_file_format == 'pdf':
                            # PDF magic number: '%PDF'
                            if first_bytes == b'%PDF':
                                is_valid_file = True
                            # Check content type
                            elif 'application/pdf' in content_type:
                                is_valid_file = True
                            # Check content disposition
                            elif 'application/octet-stream' in content_type and '.pdf' in content_disposition:
                                is_valid_file = True

                        elif book_file_format == 'epub':
                            # EPUB magic number (ZIP format): 'PK\x03\x04'
                            if first_bytes == b'PK\x03\x04':
                                is_valid_file = True
                            # Check content type
                            elif 'application/epub+zip' in content_type:
                                is_valid_file = True
                            # Check content disposition
                            elif 'application/octet-stream' in content_type and (
                                    '.epub' in content_disposition or 'epub' in content_disposition):
                                is_valid_file = True

                        if not is_valid_file:
                            last_err_msg_dl = f"Link {i + 1}: Downloaded file does not appear to be a valid {book_file_format.upper()}"
                            continue

                        # Save the file
                        with open(current_full_path, 'wb') as f:
                            f.write(first_bytes)  # write the first bytes we read
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)

                        # Verify file was saved
                        if os.path.getsize(current_full_path) > 0:
                            downloaded_successfully = True
                            break
                        else:
                            last_err_msg_dl = f"Link {i + 1}: Downloaded file is empty"
                            os.remove(current_full_path)  # remove empty file
                except requests.exceptions.RequestException as e_d:
                    last_err_msg_dl = f"Link {i + 1}: {str(e_d)}"
                    print(f"Error with link {i + 1}: {e_d}")

            if not downloaded_successfully:
                return False, last_err_msg_dl

            pdf_full_path_final = current_full_path
            print(f"File for '{book_title}' saved: {pdf_full_path_final}, Size: {os.path.getsize(pdf_full_path_final)}")
            new_book_obj = Book(
                title=book_title,
                author=book_author,
                year_published=year_p,
                cover_url=book_cover_url,
                md5=book_md5,
                pdf_path=pdf_full_path_final,
                file_format=book_file_format,
                status=0,
                user_id=current_user.id
            )
            db.session.add(new_book_obj)
            db.session.commit()
            return True, book_title

        except requests.exceptions.HTTPError as e_http:
            err_msg = f"HTTP error for '{book_title}' (MD5: {book_md5}): {e_http.response.status_code}."
            raw_error_text = e_http.response.text
            print(f"RAW HTTPError response text for {book_md5}: {raw_error_text}")
            api_err_msg_to_check = raw_error_text

            try:
                err_detail = e_http.response.json()
                api_err_msg_to_check = err_detail.get("message", raw_error_text)
            except (json.JSONDecodeError, ValueError):
                pass

            if book_md5 == original_md5:
                if "member_download endpoint" in api_err_msg_to_check.lower():
                    print(f"Detected 'member_download endpoint' requirement for original MD5 {book_md5}")
                    return "member_required", "Original book requires membership."

            err_msg += f" Response: {api_err_msg_to_check[:100]}"
            print(err_msg)
            return False, err_msg
        except Exception as e:
            print(f"Unexpected error in download attempt for '{book_title}': {e}")
            return False, f"Unexpected error: {str(e)}"
    # Main logic

    success_status, result_message = attempt_download_and_add(
        original_md5, original_title, original_author, original_year_str, original_cover_url, original_file_format
    )

    final_flash_message = ""
    final_flash_category = "danger"

    if success_status is True:
        final_flash_message = f'Book "{result_message}" added to your shelf!'
        final_flash_category = "success"
    elif success_status == "member_required":
        print(
            f"Original MD5 {original_md5} requires membership. Searching for alternatives for query: '{original_search_query}'")

        # Fallback logic
        alt_search_url = "https://annas-archive-api.p.rapidapi.com/search"
        alt_search_params = {"q": original_search_query, "ext": "pdf", "limit": "10", "sort": "most_relevant"}
        alt_search_headers = {
            "X-RapidAPI-Key": app.config['RAPIDAPI_KEY'],
            "X-RapidAPI-Host": "annas-archive-api.p.rapidapi.com"
        }
        alternative_added = False
        try:
            alt_resp = requests.get(alt_search_url, headers=alt_search_headers, params=alt_search_params, timeout=20)
            alt_resp.raise_for_status()
            alt_data_list = alt_resp.json().get('books', [])

            # Priority 1: Similar title and author
            for alt_item in alt_data_list:
                if alt_item.get('md5') == original_md5:
                    continue
                if are_strings_similar(alt_item.get('title', ''), original_title) and \
                        are_strings_similar(alt_item.get('author', ''), original_author):
                    alt_s, alt_m = attempt_download_and_add(
                        alt_item.get('md5'), alt_item.get('title'), alt_item.get('author'),
                        alt_item.get('year'), alt_item.get('imgUrl'), alt_item.get('format', 'pdf'), is_alternative=True
                    )
                    if alt_s is True:
                        final_flash_message = f'The selected version required membership. Added a similar available version: "{alt_m}".'
                        final_flash_category = "success"
                        alternative_added = True
                        break

            # Priority 2: Similar author (if nothing was added yet)
            if not alternative_added:
                for alt_item in alt_data_list:
                    if alt_item.get('md5') == original_md5:
                        continue
                    if are_strings_similar(alt_item.get('author', ''), original_author):
                        alt_s, alt_m = attempt_download_and_add(
                            alt_item.get('md5'), alt_item.get('title'), alt_item.get('author'),
                            alt_item.get('year'), alt_item.get('imgUrl'), alt_item.get('format', 'pdf'),
                            is_alternative=True
                        )
                        if alt_s is True:
                            final_flash_message = f'Selected version "{original_title}" required membership. No perfect match found, but another book by the same author was added: "{alt_m}".'
                            final_flash_category = "info"
                            alternative_added = True
                            break

            if not alternative_added:
                final_flash_message = f'Selected version of "{original_title}" may require membership, and no alternative was found.'
                final_flash_category = "warning"
        except Exception as e_alt_search:
            print(f"Error during alternative search: {e_alt_search}")
            final_flash_message = f'Selected version of "{original_title}" may require membership. An error occurred during the alternative search.'
            final_flash_category = "danger"
    else:
        # General failure
        final_flash_message = result_message
        final_flash_category = "danger"

    flash(final_flash_message, final_flash_category)

    # Delete file only if neither original nor alternative was added,
    # and if pdf_full_path_final was created (but not saved)
    if final_flash_category in ['danger', 'warning'] and pdf_full_path_final and os.path.exists(pdf_full_path_final):
        md5_from_path = os.path.basename(pdf_full_path_final).split('_')[-1].split('.')[0] if '_' in os.path.basename(
            pdf_full_path_final) else None
        if md5_from_path and not Book.query.filter_by(md5=md5_from_path).first():
            try:
                os.remove(pdf_full_path_final)
                print(f"Removed potentially orphaned file: {pdf_full_path_final}")
            except OSError:
                pass

    return redirect(url_for('home'))


@app.route('/read_book/<int:book_id>')
@login_required # Dobre jest zabezpieczenie tego widoku
def read_book(book_id):
    book = Book.query.get_or_404(book_id)
    if book.file_format == 'pdf':
        try:
            # Dla PDF, wysyłamy plik bezpośrednio do wbudowanej przeglądarki
            return send_file(book.pdf_path, as_attachment=False)
        except Exception as e:
            app.logger.error(f"Error sending PDF file {book.pdf_path}: {e}")
            flash("Could not open the PDF file.", "danger")
            return redirect(url_for('book_detail', book_id=book_id))

    elif book.file_format == 'epub':
        # Dla EPUB, renderujemy specjalny szablon z czytnikiem JS
        # Przekazujemy do szablonu URL, pod którym czytnik JS będzie mógł pobrać plik
        file_url = url_for('get_book_file', book_id=book.id)
        return render_template('epub_reader.html', book=book, epub_url=file_url)

    else:
        # Fallback na wypadek nieznanego formatu
        flash(f"Unsupported file format: '{book.file_format}'. Cannot open.", "warning")
        return redirect(url_for('book_detail', book_id=book_id))


@app.route('/get_book_file/<int:book_id>')
def get_book_file(book_id):
    """
    Ta trasa jest wywoływana przez JavaScript (czytnik Epub.js),
    aby pobrać surowy plik książki.
    """
    book = Book.query.get_or_404(book_id)

    # Dodatkowe zabezpieczenie: upewnij się, że użytkownik jest właścicielem
    if book.user_id != current_user.id:
        os.abort(403)

    if book.pdf_path and os.path.exists(book.pdf_path):
        # Tutaj po prostu wysyłamy plik, przeglądarka go nie otworzy, ale JS go pobierze
        return send_file(book.pdf_path)
    else:
        os.abort(404) # File not found

# --- Delete Book Route (also delete PDF) ---
@app.route('/remove_book/<int:book_id>', methods=['POST'])
def remove_book(book_id):
    book_to_delete = Book.query.get_or_404(book_id)
    pdf_path_to_delete = book_to_delete.pdf_path
    try:
        db.session.delete(book_to_delete)
        db.session.commit()

        if pdf_path_to_delete and os.path.exists(pdf_path_to_delete):
            try:
                os.remove(pdf_path_to_delete)
                flash(f'Book "{book_to_delete.title}" and its PDF removed from your shelf.', 'success')
            except OSError as e:
                flash(
                    f'Book "{book_to_delete.title}" removed from database, but an error occurred while deleting the PDF file: {e}',
                    'warning')
        else:
            flash(f'Book "{book_to_delete.title}" removed from your shelf.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f"Error removing book: {e}", 'danger')
    return redirect(url_for('home'))


@app.route('/toggle_favorite/<int:book_id>', methods=['POST'])
def toggle_favorite(book_id):
    book = Book.query.get_or_404(book_id)
    book.is_favorite = not book.is_favorite
    try:
        db.session.commit()
        status = "added to" if book.is_favorite else "removed from"
        flash(f'Book "{book.title}" {status} favorites.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating favorite status: {e}", 'danger')
    previous_url = request.referrer or url_for('home')
    return redirect(previous_url)


@app.route('/edit_book/<int:book_id>', methods=['GET', 'POST'])
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    categories = Category.query.all()

    if request.method == 'POST':
        try:
            category_id = request.form.get('category_id')
            book.category_id = int(category_id) if category_id else None

            new_status = int(request.form.get('status'))
            book.status = new_status

            if new_status == 1:  # Reading
                current_page_str = request.form.get('current_page')
                book.current_page = int(current_page_str) if current_page_str and current_page_str.isdigit() else 1
                if book.page_count and book.current_page > book.page_count:
                    book.current_page = book.page_count
            elif new_status == 2:  # Read
                book.current_page = book.page_count if book.page_count else 0
            else:  # To Read
                book.current_page = 0

            db.session.commit()
            flash(f'Book "{book.title}" updated successfully!', 'success')
            return redirect(url_for('home'))
        except ValueError:
            db.session.rollback()
            flash("Invalid input for current page. Please enter a valid number.", 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred while updating the book: {e}", 'danger')

    return render_template('edit_book.html', book=book, categories=categories)


@app.route('/book/<int:book_id>')
def book_detail(book_id):
    book = Book.query.get_or_404(book_id)
    return render_template('book_detail.html', book=book)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash("Username already exists!", 'user_exists')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password)
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful. Please log in.", 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            flash("Logged in successfully!", 'success')
            return redirect(url_for('home'))
        flash("User does not exist!", 'no_user')
        return redirect(url_for('login'))
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out.", 'info')
    return redirect(url_for('home'))


if __name__ == '__main__':
    # create tables if they don't exist (useful for first run without migrations)
    # with app.app_context():
    # db.create_all()
    app.run(debug=True)
