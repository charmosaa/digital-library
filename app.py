import os
from flask import Flask
from dotenv import load_dotenv
from models import db, Category, User
from flask_migrate import Migrate
from flask_login import LoginManager
from scripts.load_categories import load_categories_from_file

from routes.anna_routes import annas_archive_bp
from routes.auth_routes import auth_bp 
from routes.book_routes import book_bp
from routes.home_routes import home_bp
from routes.review_routes import review_bp
from routes.search_routes import search_bp

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


if __name__ == '__main__':
    app.run(debug=True)

# # --- Helper function to sanitize filenames ---
# def sanitize_filename(filename):
#     # delete unallowed chars and shorten
#     filename = re.sub(r'[^\w\s-]', '', filename).strip().lower()
#     filename = re.sub(r'[-\s]+', '-', filename)
#     return filename[:100]  # max 100 chars


# --- Application Views (Routes) ---
# @app.route('/')
# def home():
#     status_filter = request.args.get('status_filter')
#     only_favorites = request.args.get('only_favorites') == '1'
#     sort_by = request.args.get('sort_by')
#     category_filter = request.args.get('category_filter')

#     if current_user.is_authenticated:
#         # Pobierz UserBook dla zalogowanego użytkownika
#         query = UserBook.query.filter_by(user_id=current_user.id).join(Book)
#     else:
#         # Dla niezalogowanych - pokaż dostępne książki do dodania do kolekcji
#         return redirect(url_for('browse_books'))

#     if status_filter in ['0', '1', '2']:
#         query = query.filter(UserBook.status == int(status_filter))

#     if only_favorites:
#         query = query.filter(UserBook.is_favorite == True)

#     if category_filter and category_filter.isdigit():
#         query = query.filter(UserBook.category_id == int(category_filter))
    
#     if sort_by == 'title_asc':
#         query = query.order_by(Book.title.asc())
#     elif sort_by == 'title_desc':
#         query = query.order_by(Book.title.desc())
#     elif sort_by == 'year_desc':
#         query = query.order_by(Book.year_published.desc().nullslast())
#     elif sort_by == 'year_asc':
#         query = query.order_by(Book.year_published.asc().nullslast())
#     else:
#         query = query.order_by(UserBook.date_added.desc())

#     user_books = query.all()
#     categories = Category.query.order_by(Category.name).all() 

#     # Statystyki
#     stats = current_user.get_collection_stats()

#     return render_template(
#         'home.html',
#         user_books=user_books,
#         status_filter=status_filter,
#         only_favorites=only_favorites,
#         total_books=stats['total'],
#         to_read_count=stats['to_read'],
#         reading_count=stats['reading'],
#         read_count=stats['read'],
#         sort_by=sort_by,
#         categories=categories,
#         category_filter=category_filter
#     )


# @app.route('/browse_books')
# def browse_books():
#     """Przeglądaj wszystkie dostępne książki w systemie"""
#     query = request.args.get('query', '').strip()

#     books_query = Book.query

#     if query:
#         books_query = books_query.filter(
#             Book.title.contains(query) | Book.author.contains(query)
#         )

#     books = books_query.order_by(Book.title).all()

#     # Dla zalogowanych użytkowników - sprawdź które książki już mają
#     user_book_ids = []
#     if current_user.is_authenticated:
#         user_book_ids = [ub.book_id for ub in UserBook.query.filter_by(user_id=current_user.id).all()]

#     return render_template('browse_books.html', books=books, user_book_ids=user_book_ids, query=query)


# @app.route('/add_book_to_collection/<int:book_id>', methods=['POST'])
# @login_required
# def add_book_to_collection(book_id):
#     """Dodaj istniejącą książkę do kolekcji użytkownika"""
#     book = Book.query.get_or_404(book_id)

#     # Sprawdź czy użytkownik już ma tę książkę
#     existing = UserBook.query.filter_by(user_id=current_user.id, book_id=book_id).first()
#     if existing:
#         flash(f"You already have '{book.title}' in your collection!", 'info')
#         return redirect(url_for('book_detail', book_id=book_id))

#     # Dodaj książkę do kolekcji
#     user_book = UserBook(
#         user_id=current_user.id,
#         book_id=book_id,
#         status=0,  # Do przeczytania
#         is_favorite=False
#     )

#     try:
#         db.session.add(user_book)
#         db.session.commit()
#         flash(f"'{book.title}' added to your collection!", 'success')
#     except Exception as e:
#         db.session.rollback()
#         flash(f"Error adding book to collection: {e}", 'danger')

#     return redirect(url_for('book_detail', book_id=book_id))


# @app.route('/search', methods=['GET'])
# def search_books():
#     query = request.args.get('query', '').strip()
#     books_from_api = []
#     title_text = "Search Results"

#     if not query:
#         flash("Please enter a search query.", "info")
#         return render_template('search_results.html', books=[], query=query, title_text="Search for Books")

#     if not app.config['RAPIDAPI_KEY']:
#         flash("RapidAPI key is not configured. Please contact the administrator.", "danger")
#         return render_template('search_results.html', books=[], query=query, title_text=title_text)

#     url = "https://annas-archive-api.p.rapidapi.com/search"
#     querystring = {
#         "q": query,
#         "lang": "en",
#         "content": "book_any",
#         "ext": "pdf",
#         "sort": "most_relevant",
#         "limit": "10"
#     }
#     headers = {
#         "X-RapidAPI-Key": app.config['RAPIDAPI_KEY'],
#         "X-RapidAPI-Host": "annas-archive-api.p.rapidapi.com"
#     }

#     try:
#         response = requests.get(url, headers=headers, params=querystring, timeout=20)
#         print(f"Search API response status: {response.status_code}")
#         response.raise_for_status()
#         data = response.json()

#         if isinstance(data, dict) and 'books' in data and isinstance(data['books'], list):
#             print("API response is a dict with a 'books' list.")
#             api_response_items = data['books']
#         else:
#             print(f"API response structure not recognized. Data: {data}")

#         if api_response_items:
#             found_pdf_books = False
#             for item in api_response_items:
#                 if item.get('format', '').lower() == 'pdf':
#                     books_from_api.append({
#                         'title': item.get('title', 'No Title'),
#                         'author': item.get('author', 'No Author'),
#                         'year': item.get('year'),
#                         'cover_url': item.get('imgUrl'),
#                         'md5': item.get('md5'),
#                         'file_format': item.get('format', 'pdf')
#                     })
#                     found_pdf_books = True

#             title_text = f"Search results for '{query}' (PDFs only)"
#             if not found_pdf_books:
#                 flash(f"No PDF books found for your query '{query}'. API returned results, but none were PDFs.", 'info')
#         else:
#             flash(f"No books found in the API response for your query '{query}'.", 'info')
#             title_text = f"Search results for '{query}'"

#     except requests.exceptions.Timeout:
#         flash("The request to Anna's Archive timed out. Please try again later.", 'danger')
#     except requests.exceptions.HTTPError as e:
#         flash_message = f"Error from Anna's Archive API: {e.response.status_code}."
#         try:
#             error_detail = e.response.json()
#             flash_message += f" Message: {error_detail.get('message', e.response.text)}"
#         except ValueError:
#             flash_message += f" Response: {e.response.text[:200]}"
#         print(f"HTTPError in search_books: {flash_message}")
#         flash(flash_message, 'danger')
#     except requests.exceptions.RequestException as e:
#         print(f"RequestException in search_books: {e}")
#         flash(f"An error occurred while communicating with Anna's Archive: {e}", 'danger')
#     except json.JSONDecodeError as e:
#         print(
#             f"JSONDecodeError in search_books: {e}. Response text: {response.text[:500] if 'response' in locals() else 'N/A'}")
#         flash("Error parsing data from Anna's Archive API. Please try again.", 'danger')
#     except Exception as e:
#         print(f"Unexpected error in search_books: {e}")
#         flash(f"An unexpected error occurred during search: {e}", 'danger')

#     return render_template('search_results.html', books=books_from_api, query=query, title_text=title_text)


# def are_strings_similar(s1, s2):
#     if not s1 or not s2: return False
#     s1_clean = ''.join(filter(str.isalnum, s1)).lower()
#     s2_clean = ''.join(filter(str.isalnum, s2)).lower()
#     return s1_clean == s2_clean or s1_clean in s2_clean or s2_clean in s1_clean


# @app.route('/add_from_annas_archive', methods=['POST'])
# @login_required
# def add_from_annas_archive():
#     original_title = request.form['title']
#     original_author = request.form['author']
#     original_year_str = request.form.get('year')
#     original_cover_url = request.form.get('cover_url')
#     original_md5 = request.form.get('md5')
#     original_file_format = request.form.get('file_format', 'pdf')
#     original_search_query = request.form.get('query', original_title)

#     if not original_md5:
#         flash("MD5 hash is missing.", "danger")
#         return redirect(request.referrer or url_for('search_books'))

#     # Sprawdź czy książka już istnieje w głównej tabeli Book
#     existing_book = Book.query.filter_by(md5=original_md5).first()
#     if existing_book:
#         # Książka istnieje, sprawdź czy użytkownik ją ma w kolekcji
#         user_has_book = UserBook.query.filter_by(user_id=current_user.id, book_id=existing_book.id).first()
#         if user_has_book:
#             flash(f'You already have "{original_title}" in your collection!', 'info')
#         else:
#             # Dodaj do kolekcji użytkownika
#             user_book = UserBook(user_id=current_user.id, book_id=existing_book.id, status=0)
#             db.session.add(user_book)
#             db.session.commit()
#             flash(f'"{original_title}" added to your collection!', 'success')
#         return redirect(url_for('home'))

#     pdf_full_path_final = ""

#     # --- HELPER FUNCTION ---
#     def attempt_download_and_add(book_md5, book_title, book_author, book_year_str, book_cover_url, book_file_format,
#                                  is_alternative=False):
#         nonlocal pdf_full_path_final

#         # Sprawdź czy ta wersja już istnieje
#         existing_version = Book.query.filter_by(md5=book_md5).first()
#         if existing_version:
#             if is_alternative:
#                 print(f"Alternative MD5 {book_md5} ('{book_title}') already exists in DB. Skipping download.")
#                 return False, "Alternative version already exists."

#         year_p = None
#         if book_year_str and str(book_year_str).isdigit():
#             year_p = int(book_year_str)

#         get_links_url = "https://annas-archive-api.p.rapidapi.com/download"
#         get_links_params = {"md5": book_md5}
#         api_headers = {
#             "X-RapidAPI-Key": app.config['RAPIDAPI_KEY'],
#             "X-RapidAPI-Host": "annas-archive-api.p.rapidapi.com"
#         }

#         current_pdf_fname = f"{sanitize_filename(book_title)}_{book_md5}.{book_file_format}"
#         current_pdf_full_path = os.path.join(PDF_FOLDER, current_pdf_fname)

#         try:
#             print(f"Attempting to get links for MD5: {book_md5} ('{book_title}')")
#             links_resp = requests.get(get_links_url, headers=api_headers, params=get_links_params, timeout=30)
#             print(f"Links response for {book_md5}: {links_resp.status_code}")

#             if links_resp.status_code != 200:
#                 if book_md5 == original_md5:
#                     try:
#                         err_detail = links_resp.json()
#                         api_err_msg = err_detail.get("message", links_resp.text)
#                         if "member_download endpoint" in api_err_msg.lower():
#                             print(f"Detected 'member_download endpoint' for original MD5 {book_md5}")
#                             return "member_required", "Original book requires membership."
#                     except (json.JSONDecodeError, ValueError):
#                         pass
#                 links_resp.raise_for_status()

#             dl_links = links_resp.json()
#             if not dl_links or not isinstance(dl_links, list) or not dl_links[0]:
#                 return False, f"No download links for '{book_title}'."

#             downloaded_successfully = False
#             last_err_msg_dl = "All download links failed."

#             for i, actual_link in enumerate(dl_links):
#                 print(f"Attempting PDF from link {i + 1}/{len(dl_links)}: {actual_link} for '{book_title}'")
#                 try:
#                     pdf_dl_h = {'User-Agent': 'Mozilla/5.0...'}
#                     pdf_r = requests.get(actual_link, stream=True, timeout=180, headers=pdf_dl_h, allow_redirects=True)
#                     print(f"PDF download status from {actual_link}: {pdf_r.status_code}")
#                     pdf_r.raise_for_status()

#                     pdf_type = pdf_r.headers.get('Content-Type', '').lower()
#                     pdf_disp = pdf_r.headers.get('Content-Disposition', '')
#                     is_p = False

#                     if 'application/pdf' in pdf_type:
#                         is_p = True
#                     elif 'application/octet-stream' in pdf_type:
#                         if '.pdf' in pdf_disp.lower():
#                             is_p = True
#                         else:
#                             first_b = next(pdf_r.iter_content(4, decode_unicode=False), b'')
#                             if first_b == b'%PDF':
#                                 is_p = True
#                                 with open(current_pdf_full_path, 'wb') as f:
#                                     f.write(first_b)
#                                     [f.write(c) for c in pdf_r.iter_content(8192)]
#                                 downloaded_successfully = True
#                                 break
#                             else:
#                                 print(f"Octet-stream not PDF: {first_b}")

#                     if is_p and not downloaded_successfully:
#                         with open(current_pdf_full_path, 'wb') as f:
#                             [f.write(c) for c in pdf_r.iter_content(8192)]
#                         downloaded_successfully = True
#                         break
#                     elif not is_p:
#                         last_err_msg_dl = f"Link {i + 1} not PDF (type: {pdf_type})."

#                 except requests.exceptions.RequestException as e_d:
#                     print(f"Error with link {i + 1} for '{book_title}': {e_d}")
#                     last_err_msg_dl = f"Error with link {i + 1}: {e_d}"

#                 if downloaded_successfully:
#                     break

#             if not downloaded_successfully:
#                 return False, last_err_msg_dl

#             pdf_full_path_final = current_pdf_full_path
#             print(f"File for '{book_title}' saved: {pdf_full_path_final}, Size: {os.path.getsize(pdf_full_path_final)}")

#             # Utwórz główną książkę
#             new_book_obj = Book(
#                 title=book_title,
#                 author=book_author,
#                 year_published=year_p,
#                 cover_url=book_cover_url,
#                 md5=book_md5,
#                 pdf_path=pdf_full_path_final,
#                 file_format=book_file_format
#             )
#             db.session.add(new_book_obj)
#             db.session.flush()  # Zapisz żeby dostać ID

#             # Dodaj do kolekcji użytkownika
#             user_book = UserBook(
#                 user_id=current_user.id,
#                 book_id=new_book_obj.id,
#                 status=0
#             )
#             db.session.add(user_book)
#             db.session.commit()

#             return True, book_title

#         except requests.exceptions.HTTPError as e_http:
#             err_msg = f"HTTP error for '{book_title}' (MD5: {book_md5}): {e_http.response.status_code}."
#             raw_error_text = e_http.response.text

#             print(f"RAW HTTPError response text for {book_md5}: {raw_error_text}")

#             api_err_msg_to_check = raw_error_text

#             try:
#                 err_detail = e_http.response.json()
#                 api_err_msg_to_check = err_detail.get("message", raw_error_text)
#             except (json.JSONDecodeError, ValueError):
#                 pass

#             if book_md5 == original_md5:
#                 print(
#                     f"Checking for 'member_download endpoint' in API error: '{api_err_msg_to_check}' for original MD5 {original_md5}")

#                 if "member_download endpoint" in api_err_msg_to_check.lower():
#                     print(f"Detected 'member_download endpoint' requirement for original MD5 {book_md5}")
#                     return "member_required", "Original book requires membership."

#             err_msg += f" Response: {api_err_msg_to_check[:100]}"
#             print(err_msg)
#             return False, err_msg

#     # Main logic
#     success_status, result_message = attempt_download_and_add(
#         original_md5, original_title, original_author, original_year_str, original_cover_url, original_file_format
#     )

#     final_flash_message = ""
#     final_flash_category = "danger"

#     if success_status is True:
#         final_flash_message = f'Book "{result_message}" added to your collection!'
#         final_flash_category = "success"
#     elif success_status == "member_required":
#         print(
#             f"Original MD5 {original_md5} requires membership. Searching for alternatives for query: '{original_search_query}'")

#         # Fallback logic
#         alt_search_url = "https://annas-archive-api.p.rapidapi.com/search"
#         alt_search_params = {"q": original_search_query, "ext": "pdf", "limit": "10", "sort": "most_relevant"}
#         alt_search_headers = {
#             "X-RapidAPI-Key": app.config['RAPIDAPI_KEY'],
#             "X-RapidAPI-Host": "annas-archive-api.p.rapidapi.com"
#         }
#         alternative_added = False

#         try:
#             alt_resp = requests.get(alt_search_url, headers=alt_search_headers, params=alt_search_params, timeout=20)
#             alt_resp.raise_for_status()
#             alt_data_list = alt_resp.json().get('books', [])

#             # Priority 1: Similar title and author
#             for alt_item in alt_data_list:
#                 if alt_item.get('md5') == original_md5:
#                     continue
#                 if are_strings_similar(alt_item.get('title', ''), original_title) and \
#                         are_strings_similar(alt_item.get('author', ''), original_author):
#                     alt_s, alt_m = attempt_download_and_add(
#                         alt_item.get('md5'), alt_item.get('title'), alt_item.get('author'),
#                         alt_item.get('year'), alt_item.get('imgUrl'), alt_item.get('format', 'pdf'), is_alternative=True
#                     )
#                     if alt_s is True:
#                         final_flash_message = f'The selected version required membership. Added a similar available version: "{alt_m}".'
#                         final_flash_category = "success"
#                         alternative_added = True
#                         break

#             # Priority 2: Similar author (if nothing was added yet)
#             if not alternative_added:
#                 for alt_item in alt_data_list:
#                     if alt_item.get('md5') == original_md5:
#                         continue
#                     if are_strings_similar(alt_item.get('author', ''), original_author):
#                         alt_s, alt_m = attempt_download_and_add(
#                             alt_item.get('md5'), alt_item.get('title'), alt_item.get('author'),
#                             alt_item.get('year'), alt_item.get('imgUrl'), alt_item.get('format', 'pdf'),
#                             is_alternative=True
#                         )
#                         if alt_s is True:
#                             final_flash_message = f'Selected version "{original_title}" required membership. No perfect match found, but another book by the same author was added: "{alt_m}".'
#                             final_flash_category = "info"
#                             alternative_added = True
#                             break

#             if not alternative_added:
#                 final_flash_message = f'Selected version of "{original_title}" may require membership, and no alternative was found.'
#                 final_flash_category = "warning"
#         except Exception as e_alt_search:
#             print(f"Error during alternative search: {e_alt_search}")
#             final_flash_message = f'Selected version of "{original_title}" may require membership. An error occurred during the alternative search.'
#             final_flash_category = "danger"
#     else:
#         # General failure
#         final_flash_message = result_message
#         final_flash_category = "danger"

#     flash(final_flash_message, final_flash_category)

#     # Delete file only if neither original nor alternative was added,
#     # and if pdf_full_path_final was created (but not saved)
#     if final_flash_category in ['danger', 'warning'] and pdf_full_path_final and os.path.exists(pdf_full_path_final):
#         md5_from_path = os.path.basename(pdf_full_path_final).split('_')[-1].split('.')[0] if '_' in os.path.basename(
#             pdf_full_path_final) else None
#         if md5_from_path and not Book.query.filter_by(md5=md5_from_path).first():
#             try:
#                 os.remove(pdf_full_path_final)
#                 print(f"Removed potentially orphaned file: {pdf_full_path_final}")
#             except OSError:
#                 pass

#     return redirect(url_for('home'))


# # # --- Route to serve/read PDF files ---
# # @app.route('/read_book/<int:book_id>')
# # @login_required
# # def read_book(book_id):
# #     book = Book.query.get_or_404(book_id)

# #     # Sprawdź czy użytkownik ma tę książkę w kolekcji
# #     user_book = UserBook.query.filter_by(user_id=current_user.id, book_id=book_id).first()
# #     if not user_book:
# #         flash("You don't have this book in your collection!", 'danger')
# #         return redirect(url_for('book_detail', book_id=book_id))

# #     if book.pdf_path and os.path.exists(book.pdf_path):
# #         try:
# #             return send_file(book.pdf_path, as_attachment=False)
# #         except Exception as e:
# #             app.logger.error(f"Error sending file {book.pdf_path}: {e}")
# #             flash("Could not open the book file.", "danger")
# #             return redirect(url_for('book_detail', book_id=book_id))
# #     else:
# #         flash("PDF file not found for this book.", "danger")
# #         return redirect(url_for('book_detail', book_id=book_id))


# # # --- Delete Book Route (usuwa z kolekcji użytkownika) ---
# # @app.route('/remove_book/<int:book_id>', methods=['POST'])
# # @login_required
# # def remove_book(book_id):
# #     """Usuń książkę z kolekcji użytkownika (nie usuwa głównej książki)"""
# #     user_book = UserBook.query.filter_by(user_id=current_user.id, book_id=book_id).first()

# #     if not user_book:
# #         flash("You don't have this book in your collection!", 'danger')
# #         return redirect(url_for('home'))

# #     book_title = user_book.book.title

# #     try:
# #         db.session.delete(user_book)
# #         db.session.commit()
# #         flash(f'Book "{book_title}" removed from your collection.', 'success')
# #     except Exception as e:
# #         db.session.rollback()
# #         flash(f"Error removing book: {e}", 'danger')

# #     return redirect(url_for('home'))


# # @app.route('/toggle_favorite/<int:book_id>', methods=['POST'])
# # @login_required
# # def toggle_favorite(book_id):
#     user_book = UserBook.query.filter_by(user_id=current_user.id, book_id=book_id).first()

#     if not user_book:
#         flash("You don't have this book in your collection!", 'danger')
#         return redirect(url_for('book_detail', book_id=book_id))

#     user_book.is_favorite = not user_book.is_favorite

#     try:
#         db.session.commit()
#         status = "added to" if user_book.is_favorite else "removed from"
#         flash(f'Book "{user_book.book.title}" {status} favorites.', 'success')
#     except Exception as e:
#         db.session.rollback()
#         flash(f"Error updating favorite status: {e}", 'danger')

#     previous_url = request.referrer or url_for('home')
#     return redirect(previous_url)


# @app.route('/edit_book/<int:book_id>', methods=['GET', 'POST'])
# @login_required
# def edit_book(book_id):
#     book = Book.query.get_or_404(book_id)
#     user_book = UserBook.query.filter_by(user_id=current_user.id, book_id=book_id).first()

#     if not user_book:
#         flash("You don't have this book in your collection!", 'danger')
#         return redirect(url_for('book_detail', book_id=book_id))

#     categories = Category.query.all()

#     if request.method == 'POST':
#         try:
#             category_id = request.form.get('category_id')
#             user_book.category_id = int(category_id) if category_id else None

#             new_status = int(request.form.get('status'))
#             user_book.status = new_status

#             if new_status == 1:  # Reading
#                 current_page_str = request.form.get('current_page')
#                 user_book.current_page = int(current_page_str) if current_page_str and current_page_str.isdigit() else 1
#                 if book.page_count and user_book.current_page > book.page_count:
#                     user_book.current_page = book.page_count
#             elif new_status == 2:  # Read
#                 user_book.current_page = book.page_count if book.page_count else 0
#             else:  # To Read
#                 user_book.current_page = 0

#             db.session.commit()
#             flash(f'Book "{book.title}" updated successfully!', 'success')
#             return redirect(url_for('home'))
#         except ValueError:
#             db.session.rollback()
#             flash("Invalid input for current page. Please enter a valid number.", 'danger')
#         except Exception as e:
#             db.session.rollback()
#             flash(f"An error occurred while updating the book: {e}", 'danger')

#     return render_template('edit_book.html', book=book, user_book=user_book, categories=categories)


# @app.route('/book/<int:book_id>')
# def book_detail(book_id):
#     book = Book.query.get_or_404(book_id)

#     user_book = None
#     if current_user.is_authenticated:
#         user_book = UserBook.query.filter_by(user_id=current_user.id, book_id=book_id).first()

#     return render_template('book_detail.html', book=book, user_book=user_book)


# # --- REVIEW ROUTES ---
# @app.route('/book/<int:book_id>/add_review', methods=['POST'])
# @login_required
# def add_review(book_id):
#     """Dodawanie nowej recenzji"""
#     book = Book.query.get_or_404(book_id)

#     # Sprawdź czy użytkownik już ma recenzję dla tej książki
#     existing_review = Review.query.filter_by(book_id=book_id, user_id=current_user.id).first()
#     if existing_review:
#         flash("You already have a review for this book. You can edit it instead.", 'warning')
#         return redirect(url_for('book_detail', book_id=book_id))

#     try:
#         rating = request.form.get('rating')
#         comment = request.form.get('comment', '').strip()

#         # Walidacja
#         if not rating and not comment:
#             flash("Please provide either a rating or a comment.", 'warning')
#             return redirect(url_for('book_detail', book_id=book_id))

#         if rating and (not rating.isdigit() or int(rating) < 1 or int(rating) > 5):
#             flash("Rating must be between 1 and 5.", 'danger')
#             return redirect(url_for('book_detail', book_id=book_id))

#         # Tworzenie nowej recenzji
#         new_review = Review(
#             rating=int(rating) if rating else None,
#             comment=comment if comment else None,
#             user_id=current_user.id,
#             book_id=book_id
#         )

#         db.session.add(new_review)
#         db.session.commit()

#         flash("Your review has been added successfully!", 'success')

#     except Exception as e:
#         db.session.rollback()
#         flash(f"Error adding review: {e}", 'danger')

#     return redirect(url_for('book_detail', book_id=book_id))


# @app.route('/book/<int:book_id>/edit_review/<int:review_id>', methods=['POST'])
# @login_required
# def edit_review(book_id, review_id):
#     """Edytowanie istniejącej recenzji"""
#     review = Review.query.get_or_404(review_id)

#     # Sprawdź czy recenzja należy do aktualnego użytkownika
#     if review.user_id != current_user.id:
#         flash("You can only edit your own reviews.", 'danger')
#         return redirect(url_for('book_detail', book_id=book_id))

#     try:
#         rating = request.form.get('rating')
#         comment = request.form.get('comment', '').strip()

#         # Walidacja
#         if not rating and not comment:
#             flash("Please provide either a rating or a comment.", 'warning')
#             return redirect(url_for('book_detail', book_id=book_id))

#         if rating and (not rating.isdigit() or int(rating) < 1 or int(rating) > 5):
#             flash("Rating must be between 1 and 5.", 'danger')
#             return redirect(url_for('book_detail', book_id=book_id))

#         # Aktualizacja recenzji
#         review.rating = int(rating) if rating else None
#         review.comment = comment if comment else None
#         review.date_modified = datetime.utcnow()

#         db.session.commit()
#         flash("Your review has been updated successfully!", 'success')

#     except Exception as e:
#         db.session.rollback()
#         flash(f"Error updating review: {e}", 'danger')

#     return redirect(url_for('book_detail', book_id=book_id))


# @app.route('/book/<int:book_id>/delete_review/<int:review_id>', methods=['POST'])
# @login_required
# def delete_review(book_id, review_id):
#     """Usuwanie recenzji"""
#     review = Review.query.get_or_404(review_id)

#     # Sprawdź czy recenzja należy do aktualnego użytkownika
#     if review.user_id != current_user.id:
#         flash("You can only delete your own reviews.", 'danger')
#         return redirect(url_for('book_detail', book_id=book_id))

#     try:
#         db.session.delete(review)
#         db.session.commit()
#         flash("Your review has been deleted.", 'info')

#     except Exception as e:
#         db.session.rollback()
#         flash(f"Error deleting review: {e}", 'danger')

#     return redirect(url_for('book_detail', book_id=book_id))


# # --- USER AUTHENTICATION ROUTES ---
# @login_manager.user_loader
# def load_user(user_id):
#     return User.query.get(int(user_id))


# # @app.route('/register', methods=['GET', 'POST'])
# # def register():
# #     if request.method == 'POST':
# #         username = request.form['username']
# #         password = request.form['password']
# #         if User.query.filter_by(username=username).first():
# #             flash("Username already exists!", 'user_exists')
# #             return redirect(url_for('register'))

# #         hashed_pw = generate_password_hash(password)
# #         new_user = User(username=username, password=hashed_pw)
# #         db.session.add(new_user)
# #         db.session.commit()
# #         flash("Registration successful. Please log in.", 'success')
# #         return redirect(url_for('login'))

# #     return render_template('register.html')


# # @app.route('/login', methods=['GET', 'POST'])
# # def login():
# #     if request.method == 'POST':
# #         user = User.query.filter_by(username=request.form['username']).first()
# #         if user and check_password_hash(user.password, request.form['password']):
# #             login_user(user)
# #             flash("Logged in successfully!", 'success')
# #             return redirect(url_for('home'))
# #         flash("User does not exist!", 'no_user')
# #         return redirect(url_for('login'))
# #     return render_template('login.html')


# # @app.route('/logout')
# # @login_required
# # def logout():
# #     logout_user()
# #     flash("Logged out.", 'info')
# #     return redirect(url_for('browse_books'))


# if __name__ == '__main__':
#     app.run(debug=True)