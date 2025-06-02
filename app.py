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


load_dotenv()

app = Flask(__name__)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# --- App Configuration and Database ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'  # Baza danych będzie w instance/site.db
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['RAPIDAPI_KEY'] = os.getenv('RAPIDAPI_KEY')

# Folder do przechowywania pobranych PDFów
PDF_FOLDER = os.path.join(app.instance_path, 'pdfs')
os.makedirs(PDF_FOLDER, exist_ok=True)  # Upewnij się, że folder istnieje

db.init_app(app)
migrate = Migrate(app, db)


# --- Helper function to sanitize filenames ---
def sanitize_filename(filename):
    # Usuń niedozwolone znaki i skróć, jeśli zbyt długie
    filename = re.sub(r'[^\w\s-]', '', filename).strip().lower()
    filename = re.sub(r'[-\s]+', '-', filename)
    return filename[:100]  # Ogranicz długość


# --- Application Views (Routes) ---
@app.route('/')
def home():
    status_filter = request.args.get('status_filter')
    only_favorites = request.args.get('only_favorites') == '1'
    sort_by = request.args.get('sort_by')

    if current_user.is_authenticated:
        query = Book.query.filter_by(user_id=current_user.id)
    else:
        query = Book.query.filter_by(user_id=None)  # Pokaż tylko książki niezalogowane

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
            new_book.category_id = int(category_id) if category_id else None  # Upewnij się, że konwertujesz na int

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
        "q": query,
        "lang": "en",
        "content": "book_any",
        "ext": "pdf",
        "sort": "most_relevant", # lub "newest"
        "limit": "10"
    }
    headers = {
        "X-RapidAPI-Key": app.config['RAPIDAPI_KEY'],
        "X-RapidAPI-Host": "annas-archive-api.p.rapidapi.com"
    }

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=20)
        print(f"Search API response status: {response.status_code}") # Loguj status
        response.raise_for_status()
        data = response.json()
        #print(f"Search API response data: {json.dumps(data, indent=2)}") # Loguj całą odpowiedź JSON (dla debugowania)

        # --- ZMIANA TUTAJ ---
        # Sprawdź, czy odpowiedź jest słownikiem i zawiera klucz 'books',
        # oraz czy wartość pod tym kluczem jest listą.
        if isinstance(data, dict) and 'books' in data and isinstance(data['books'], list):
            print("API response is a dict with a 'books' list.")
            api_response_items = data['books']  # Przypisz listę książek
        else:
            # Ten warunek jest teraz bardziej precyzyjny dla tego API
            print(
                f"API response structure not recognized (expected dict with 'books' list) or 'books' list is empty. Data: {data}")
            # Komunikat flash już jest niżej, jeśli api_response_items pozostanie puste

        if api_response_items:
            found_pdf_books = False  # Flaga do sprawdzenia, czy znaleziono jakiekolwiek PDFy
            for item in api_response_items:
                # Używamy nazw pól z odpowiedzi JSON
                if item.get('format', '').lower() == 'pdf':  # Pole nazywa się 'format'
                    books_from_api.append({
                        'title': item.get('title', 'No Title'),
                        'author': item.get('author', 'No Author'),  # Pole nazywa się 'author'
                        'year': item.get('year'),  # Pole nazywa się 'year'
                        'cover_url': item.get('imgUrl'),  # Pole nazywa się 'imgUrl'
                        'md5': item.get('md5'),  # Pole nazywa się 'md5'
                        'file_format': item.get('format', 'pdf')  # Pole nazywa się 'format'
                    })
                    found_pdf_books = True

            title_text = f"Search results for '{query}' (PDFs only)"
            if not found_pdf_books:  # Jeśli pętla przeszła, ale nie dodała żadnych książek (nie było PDFów)
                flash(f"No PDF books found for your query '{query}'. API returned results, but none were PDFs.", 'info')
        else:  # Jeśli api_response_items jest puste po sprawdzeniu struktury lub klucz 'books' nie istnieje/jest pusty
            flash(f"No books found in the API response for your query '{query}'.", 'info')
            title_text = f"Search results for '{query}'"


    except requests.exceptions.Timeout:
        flash("The request to Anna's Archive timed out. Please try again later.", 'danger')
    except requests.exceptions.HTTPError as e:
        flash_message = f"Error from Anna's Archive API: {e.response.status_code}."
        try:
            error_detail = e.response.json() # Spróbuj odczytać JSON z błędu
            flash_message += f" Message: {error_detail.get('message', e.response.text)}"
        except ValueError: # Jeśli odpowiedź błędu nie jest JSON
            flash_message += f" Response: {e.response.text[:200]}"
        print(f"HTTPError in search_books: {flash_message}") # Loguj do konsoli
        flash(flash_message, 'danger')
    except requests.exceptions.RequestException as e:
        print(f"RequestException in search_books: {e}")
        flash(f"An error occurred while communicating with Anna's Archive: {e}", 'danger')
    except json.JSONDecodeError as e: # Zmieniono z ValueError na bardziej specyficzny błąd
        print(f"JSONDecodeError in search_books: {e}. Response text: {response.text[:500] if 'response' in locals() else 'N/A'}")
        flash("Error parsing data from Anna's Archive API. Please try again.", 'danger')
    except Exception as e: # Ogólny wyjątek na końcu
        print(f"Unexpected error in search_books: {e}")
        flash(f"An unexpected error occurred during search: {e}", 'danger')


    return render_template('search_results.html', books=books_from_api, query=query, title_text=title_text)


def are_strings_similar(s1, s2):  # Definicja, jeśli jeszcze jej nie masz globalnie
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

    # Sprawdź, czy książka o tym MD5 (oryginalnym) już istnieje
    # Robimy to tutaj, aby uniknąć dodawania duplikatu, jeśli oryginalna jest już na półce
    existing_book_original_md5 = Book.query.filter_by(md5=original_md5).first()
    if existing_book_original_md5:
        flash(f'Książka "{original_title}" (ta konkretna wersja) jest już na Twojej półce!', 'info')
        return redirect(url_for('home'))

    pdf_full_path_final = ""  # Ścieżka do ostatecznie pobranego pliku

    # --- FUNKCJA POMOCNICZA ---
    def attempt_download_and_add(book_md5, book_title, book_author, book_year_str, book_cover_url, book_file_format,
                                 is_alternative=False):
        nonlocal pdf_full_path_final
        # Sprawdź, czy TA WERSJA (MD5) już istnieje, zanim zaczniesz pobierać
        # To ważne, jeśli alternatywa ma ten sam MD5 co już istniejąca inna książka
        # lub jeśli oryginalna książka została dodana w międzyczasie (mało prawdopodobne, ale bezpieczniej)
        existing_version = Book.query.filter_by(md5=book_md5).first()
        if existing_version:
            # Jeśli to alternatywa i już istnieje, to sukces - nie trzeba pobierać
            if is_alternative:
                print(f"Alternative MD5 {book_md5} ('{book_title}') already exists in DB. Skipping download.")
                # Możemy tu zwrócić specjalny status, aby główna logika wiedziała, że nie trzeba nic robić,
                # ale też nie jest to błąd. Na razie potraktujmy to jako "sukces", bo książka jest.
                # Albo po prostu nie róbmy nic i pozwólmy pętli szukać dalej, jeśli chcemy unikalne MD5.
                # Dla uproszczenia, na razie potraktujmy to jako nieudaną próbę dodania TEJ alternatywy.
                return False, "Alternative version already in collection."
                # Jeśli to oryginalna próba, a książka została dodana przez inny proces, to też dobrze.
            # Ten przypadek jest obsłużony przed wywołaniem attempt_download_and_add.

        year_p = None
        if book_year_str and str(book_year_str).isdigit(): year_p = int(book_year_str)

        get_links_url = "https://annas-archive-api.p.rapidapi.com/download"
        get_links_params = {"md5": book_md5}
        api_headers = {
            "X-RapidAPI-Key": app.config['RAPIDAPI_KEY'],
            "X-RapidAPI-Host": "annas-archive-api.p.rapidapi.com"
        }

        current_pdf_fname = f"{sanitize_filename(book_title)}_{book_md5}.{book_file_format}"
        current_pdf_full_path = os.path.join(PDF_FOLDER, current_pdf_fname)

        try:
            print(f"Attempting to get links for MD5: {book_md5} ('{book_title}')")
            links_resp = requests.get(get_links_url, headers=api_headers, params=get_links_params, timeout=30)
            print(f"Links response for {book_md5}: {links_resp.status_code}")

            if links_resp.status_code != 200:
                if book_md5 == original_md5:  # Tylko dla oryginalnej książki sprawdzamy member_required
                    try:
                        err_detail = links_resp.json()
                        api_err_msg = err_detail.get("message", links_resp.text)
                        if "member_download endpoint" in api_err_msg.lower():
                            print(f"Detected 'member_download endpoint' for original MD5 {book_md5}")
                            return "member_required", "Original book requires membership."
                    except (json.JSONDecodeError, ValueError):
                        pass
                links_resp.raise_for_status()  # Jeśli nie member_required, rzuć błąd

            dl_links = links_resp.json()
            if not dl_links or not isinstance(dl_links, list) or not dl_links[0]:
                return False, f"No download links for '{book_title}'."

            downloaded_successfully = False
            last_err_msg_dl = "All download links failed."
            for i, actual_link in enumerate(dl_links):
                print(f"Attempting PDF from link {i + 1}/{len(dl_links)}: {actual_link} for '{book_title}'")
                try:
                    pdf_dl_h = {'User-Agent': 'Mozilla/5.0...'}
                    pdf_r = requests.get(actual_link, stream=True, timeout=180, headers=pdf_dl_h, allow_redirects=True)
                    print(f"PDF download status from {actual_link}: {pdf_r.status_code}")
                    pdf_r.raise_for_status()

                    pdf_type = pdf_r.headers.get('Content-Type', '').lower()
                    pdf_disp = pdf_r.headers.get('Content-Disposition', '')
                    is_p = False
                    if 'application/pdf' in pdf_type:
                        is_p = True
                    elif 'application/octet-stream' in pdf_type:
                        if '.pdf' in pdf_disp.lower():
                            is_p = True
                        else:
                            first_b = next(pdf_r.iter_content(4, decode_unicode=False), b'')
                            if first_b == b'%PDF':
                                is_p = True
                                with open(current_pdf_full_path, 'wb') as f:
                                    f.write(first_b); [f.write(c) for c in pdf_r.iter_content(8192)]
                                downloaded_successfully = True;
                                break
                            else:
                                print(f"Octet-stream not PDF: {first_b}")

                    if is_p and not downloaded_successfully:  # Jeśli nie zapisano przez first_b
                        with open(current_pdf_full_path, 'wb') as f:
                            [f.write(c) for c in pdf_r.iter_content(8192)]
                        downloaded_successfully = True;
                        break
                    elif not is_p:
                        last_err_msg_dl = f"Link {i + 1} not PDF (type: {pdf_type})."

                except requests.exceptions.RequestException as e_d:
                    print(f"Error with link {i + 1} for '{book_title}': {e_d}")
                    last_err_msg_dl = f"Error with link {i + 1}: {e_d}"
                if downloaded_successfully: break

            if not downloaded_successfully: return False, last_err_msg_dl

            pdf_full_path_final = current_pdf_full_path  # Ustaw globalną ścieżkę
            print(f"File for '{book_title}' saved: {pdf_full_path_final}, Size: {os.path.getsize(pdf_full_path_final)}")
            new_book_obj = Book(title=book_title, author=book_author, year_published=year_p,
                                cover_url=book_cover_url, md5=book_md5, pdf_path=pdf_full_path_final,
                                file_format=book_file_format, status=0,user_id=current_user.id)
            db.session.add(new_book_obj)
            db.session.commit()
            return True, book_title  # Zwróć pobrany tytuł dla komunikatu



        except requests.exceptions.HTTPError as e_http:

            err_msg = f"HTTP error for '{book_title}' (MD5: {book_md5}): {e_http.response.status_code}."

            raw_error_text = e_http.response.text  # Zapisz oryginalny tekst błędu

            print(f"RAW HTTPError response text for {book_md5}: {raw_error_text}")

            api_err_msg_to_check = raw_error_text  # Domyślnie użyj surowego tekstu

            try:

                # Spróbuj sparsować jako JSON, jeśli się da, aby uzyskać bardziej strukturalny komunikat

                err_detail = e_http.response.json()

                api_err_msg_to_check = err_detail.get("message",
                                                      raw_error_text)  # Użyj 'message' jeśli jest, inaczej surowy tekst

            except (json.JSONDecodeError, ValueError):

                pass  # Nie udało się sparsować jako JSON, api_err_msg_to_check pozostaje raw_error_text

            # Teraz sprawdzaj member_download endpoint na podstawie api_err_msg_to_check

            # Ta logika powinna być teraz tylko dla oryginalnego MD5, jeśli chcemy fallback tylko dla niego

            if book_md5 == original_md5:  # Upewnij się, że original_md5 jest dostępne z zasięgu nadrzędnego

                print(
                    f"Checking for 'member_download endpoint' in API error: '{api_err_msg_to_check}' for original MD5 {original_md5}")

                if "member_download endpoint" in api_err_msg_to_check.lower():
                    print(f"Detected 'member_download endpoint' requirement for original MD5 {book_md5}")

                    return "member_required", "Original book requires membership."

            # Jeśli nie "member_required" lub nie oryginalna książka, zbuduj ogólny komunikat błędu

            err_msg += f" Response: {api_err_msg_to_check[:100]}"  # Dodaj fragment komunikatu (JSON lub tekst)

            print(err_msg)

            return False, err_msg
    # Główna logika
    success_status, result_message = attempt_download_and_add(
        original_md5, original_title, original_author, original_year_str, original_cover_url, original_file_format
    )

    final_flash_message = ""
    final_flash_category = "danger"

    if success_status is True:
        final_flash_message = f'Książka "{result_message}" dodana na Twoją półkę!'
        final_flash_category = "success"
    elif success_status == "member_required":
        print(
            f"Original MD5 {original_md5} requires membership. Searching for alternatives for query: '{original_search_query}'")
        # Logika Fallback
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

            # Priorytet 1: Podobny tytuł i autor
            for alt_item in alt_data_list:
                if alt_item.get('md5') == original_md5: continue
                if are_strings_similar(alt_item.get('title', ''), original_title) and \
                        are_strings_similar(alt_item.get('author', ''), original_author):
                    alt_s, alt_m = attempt_download_and_add(
                        alt_item.get('md5'), alt_item.get('title'), alt_item.get('author'),
                        alt_item.get('year'), alt_item.get('imgUrl'), alt_item.get('format', 'pdf'), is_alternative=True
                    )
                    if alt_s is True:
                        final_flash_message = f'Wybrana wersja wymagała konta premium. Dodano podobną, dostępną wersję: "{alt_m}".'
                        final_flash_category = "success"  # Lub "info" jeśli chcesz inaczej oznaczyć
                        alternative_added = True;
                        break

            # Priorytet 2: Podobny autor (jeśli nic wcześniej)
            if not alternative_added:
                for alt_item in alt_data_list:
                    if alt_item.get('md5') == original_md5: continue
                    if are_strings_similar(alt_item.get('author', ''), original_author):
                        alt_s, alt_m = attempt_download_and_add(
                            alt_item.get('md5'), alt_item.get('title'), alt_item.get('author'),
                            alt_item.get('year'), alt_item.get('imgUrl'), alt_item.get('format', 'pdf'),
                            is_alternative=True
                        )
                        if alt_s is True:
                            final_flash_message = f'Wybrana wersja "{original_title}" wymagała konta premium. Nie znaleziono idealnie pasującej alternatywy, ale dodano inną książkę tego samego autora: "{alt_m}".'
                            final_flash_category = "info"
                            alternative_added = True;
                            break

            if not alternative_added:
                final_flash_message = f'Wybrana wersja książki "{original_title}" może wymagać konta premium i nie znaleziono dostępnej alternatywy.'
                final_flash_category = "warning"
        except Exception as e_alt_search:
            print(f"Error during alternative search: {e_alt_search}")
            final_flash_message = f'Wybrana wersja książki "{original_title}" może wymagać konta premium. Wystąpił błąd podczas szukania alternatyw.'
            final_flash_category = "danger"
    else:  # Inny błąd (success_status is False)
        final_flash_message = result_message  # Komunikat z attempt_download_and_add
        final_flash_category = "danger"

    flash(final_flash_message, final_flash_category)

    # Usuń plik tylko jeśli nie było absolutnie żadnego sukcesu (ani oryginał, ani alternatywa)
    # i jeśli pdf_full_path_final nie wskazuje na pomyślnie dodany plik.
    # To jest trudne do precyzyjnego określenia bez sprawdzania, czy książka ostatecznie trafiła do bazy.
    # Prostsze: jeśli final_flash_category to 'danger' lub 'warning', a pdf_full_path_final jest ustawione (ale nieudane)
    if final_flash_category in ['danger', 'warning'] and pdf_full_path_final and os.path.exists(pdf_full_path_final):
        # Sprawdź, czy książka o tym MD5 (z pdf_full_path_final) jest w bazie
        # To wymaga wyciągnięcia MD5 z pdf_full_path_final
        md5_from_path = os.path.basename(pdf_full_path_final).split('_')[-1].split('.')[0] if '_' in os.path.basename(
            pdf_full_path_final) else None
        if md5_from_path and not Book.query.filter_by(md5=md5_from_path).first():
            try:
                os.remove(pdf_full_path_final); print(f"Removed potentially orphaned file: {pdf_full_path_final}")
            except OSError:
                pass

    return redirect(url_for('home'))


# --- Route to serve/read PDF files ---
@app.route('/read_book/<int:book_id>')
def read_book(book_id):
    book = Book.query.get_or_404(book_id)
    if book.pdf_path and os.path.exists(book.pdf_path):
        # send_file jest lepsze, bo może próbować ustawić odpowiedni Content-Type
        # i pozwala na wyświetlanie w przeglądarce (as_attachment=False)
        try:
            return send_file(book.pdf_path, as_attachment=False)
        except Exception as e:
            app.logger.error(f"Error sending file {book.pdf_path}: {e}")
            flash("Could not open the book file.", "danger")
            return redirect(url_for('book_detail', book_id=book_id))
    else:
        flash("PDF file not found for this book.", "danger")
        return redirect(url_for('book_detail', book_id=book_id))


# --- Delete Book Route (aktualizacja: usuń też plik PDF) ---
@app.route('/remove_book/<int:book_id>', methods=['POST'])
def remove_book(book_id):
    book_to_delete = Book.query.get_or_404(book_id)
    pdf_path_to_delete = book_to_delete.pdf_path  # Zachowaj ścieżkę przed usunięciem obiektu
    try:
        db.session.delete(book_to_delete)
        db.session.commit()

        # Usuń plik PDF, jeśli istnieje
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
                book.current_page = int(current_page_str) if current_page_str and current_page_str.isdigit() else 0
                if book.page_count and book.current_page > book.page_count:  # Walidacja
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
            flash("Nazwa użytkownika już istnieje!", 'user_exists')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password)
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash("Rejestracja zakończona sukcesem. Zaloguj się.", 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            flash("Zalogowano pomyślnie!", 'success')
            return redirect(url_for('home'))
        flash("Konto nie istnieje!", 'no_user')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Wylogowano.", 'info')
    return redirect(url_for('home'))


if __name__ == '__main__':
    # Utwórz tabele, jeśli nie istnieją (dla pierwszego uruchomienia bez migracji)
    # with app.app_context():
    # db.create_all()
    app.run(debug=True)