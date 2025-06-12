import json
import os
import requests

from flask import current_app
from flask_login import current_user
from models import db, Book, UserBook
from utils.string_utils import are_strings_similar, sanitize_filename


def get_pdf_folder():
    """Zwraca ścieżkę do folderu z książkami i tworzy go, jeśli nie istnieje."""
    folder = os.path.join(current_app.instance_path, 'pdfs')
    os.makedirs(folder, exist_ok=True)
    return folder


def attempt_download_and_add(book_md5, book_title, book_author, book_year_str, book_cover_url,
                             book_file_format, is_alternative=False, original_md5=None):
    """
    Próbuje pobrać, zweryfikować i dodać książkę (PDF lub EPUB) do bazy danych i kolekcji użytkownika.
    """
    final_file_path = None

    existing_version = Book.query.filter_by(md5=book_md5).first()
    if existing_version:
        if is_alternative:
            print(f"Alternative MD5 {book_md5} ('{book_title}') already exists in DB. Skipping download.")
            return False, "Alternative version already exists.", None

    year_p = int(book_year_str) if book_year_str and str(book_year_str).isdigit() else None

    get_links_url = "https://annas-archive-api.p.rapidapi.com/download"
    get_links_params = {"md5": book_md5}
    api_headers = {
        "X-RapidAPI-Key": current_app.config['RAPIDAPI_KEY'],
        "X-RapidAPI-Host": "annas-archive-api.p.rapidapi.com"
    }

    pdf_folder = get_pdf_folder()
    sanitized_title = sanitize_filename(book_title)
    current_file_fname = f"{sanitized_title}_{book_md5}.{book_file_format}"
    current_file_full_path = os.path.join(pdf_folder, current_file_fname)

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
                        return "member_required", "Original book requires membership.", None
                except (json.JSONDecodeError, ValueError):
                    pass
            links_resp.raise_for_status()

        dl_links = links_resp.json()
        if not dl_links or not isinstance(dl_links, list) or not dl_links[0]:
            return False, f"No download links for '{book_title}'.", None

        downloaded_successfully = False
        last_err_msg_dl = "All download links failed."

        for i, actual_link in enumerate(dl_links):
            print(
                f"Attempting {book_file_format.upper()} from link {i + 1}/{len(dl_links)}: {actual_link} for '{book_title}'")
            try:
                dl_headers = {'User-Agent': 'Mozilla/5.0...'}
                response = requests.get(actual_link, stream=True, timeout=180, headers=dl_headers, allow_redirects=True)
                print(f"Download status from {actual_link}: {response.status_code}")
                response.raise_for_status()

                content_type = response.headers.get('Content-Type', '').lower()
                content_disp = response.headers.get('Content-Disposition', '')
                is_valid_format = False

                if book_file_format == 'pdf' and 'application/pdf' in content_type:
                    is_valid_format = True
                elif book_file_format == 'epub' and 'application/epub+zip' in content_type:
                    is_valid_format = True
                elif 'application/octet-stream' in content_type:
                    if f'.{book_file_format}' in content_disp.lower():
                        is_valid_format = True
                    else:
                        first_bytes = next(response.iter_content(4, decode_unicode=False), b'')
                        if book_file_format == 'pdf' and first_bytes == b'%PDF':
                            is_valid_format = True
                        elif book_file_format == 'epub' and first_bytes == b'PK\x03\x04':
                            is_valid_format = True

                        if is_valid_format:
                            with open(current_file_full_path, 'wb') as f:
                                f.write(first_bytes)
                                for chunk in response.iter_content(8192):
                                    f.write(chunk)
                            downloaded_successfully = True
                            break
                        else:
                            print(f"Octet-stream is not a valid {book_file_format.upper()}: first bytes {first_bytes}")

                if is_valid_format and not downloaded_successfully:
                    with open(current_file_full_path, 'wb') as f:
                        for chunk in response.iter_content(8192):
                            f.write(chunk)
                    downloaded_successfully = True
                    break
                elif not is_valid_format:
                    last_err_msg_dl = f"Link {i + 1} not a valid {book_file_format.upper()} (type: {content_type})."

            except requests.exceptions.RequestException as e_d:
                print(f"Error with link {i + 1} for '{book_title}': {e_d}")
                last_err_msg_dl = f"Error with link {i + 1}: {e_d}"

            if downloaded_successfully:
                break

        if not downloaded_successfully:
            return False, last_err_msg_dl, None

        final_file_path = current_file_full_path
        print(f"File for '{book_title}' saved: {final_file_path}, Size: {os.path.getsize(final_file_path)}")

        new_book_obj = Book(
            title=book_title,
            author=book_author,
            year_published=year_p,
            cover_url=book_cover_url,
            md5=book_md5,
            pdf_path=final_file_path,
            file_format=book_file_format
        )
        db.session.add(new_book_obj)
        db.session.flush()

        user_book = UserBook(
            user_id=current_user.id,
            book_id=new_book_obj.id,
            status=0
        )
        db.session.add(user_book)
        db.session.commit()

        return True, book_title, final_file_path

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
            print(
                f"Checking for 'member_download endpoint' in API error: '{api_err_msg_to_check}' for original MD5 {original_md5}")
            if "member_download endpoint" in api_err_msg_to_check.lower():
                print(f"Detected 'member_download endpoint' requirement for original MD5 {book_md5}")
                return "member_required", "Original book requires membership.", None

        err_msg += f" Response: {api_err_msg_to_check[:100]}"
        print(err_msg)
        return False, err_msg, None
    except Exception as e:
        print(f"An unexpected error in attempt_download_and_add: {e}")
        db.session.rollback()
        return False, f"An unexpected error occurred: {e}", None


def try_add_original_or_alternatives(original_title, original_author, original_year_str, original_cover_url,
                                     original_md5, original_file_format, original_search_query, user):
    """
    Główna logika biznesowa: próbuje dodać oryginalną książkę, a w razie niepowodzenia
    szuka i próbuje dodać wersje alternatywne.
    """
    success_status, result_message, final_file_path = attempt_download_and_add(
        original_md5, original_title, original_author, original_year_str, original_cover_url, original_file_format,
        original_md5=original_md5
    )

    final_flash_message = ""
    final_flash_category = "danger"

    if success_status is True:
        final_flash_message = f'Book "{result_message}" added to your collection!'
        final_flash_category = "success"

    elif success_status == "member_required" or success_status is False:
        print(f"Original download failed: {result_message}. Starting prioritized alternative search...")

        alt_search_url = "https://annas-archive-api.p.rapidapi.com/search"
        alt_search_params = {"q": original_search_query, "content": "book_any", "limit": "20", "sort": "most_relevant"}
        alt_search_headers = {
            "X-RapidAPI-Key": current_app.config['RAPIDAPI_KEY'],
            "X-RapidAPI-Host": "annas-archive-api.p.rapidapi.com"
        }
        alternative_added = False
        alt_data_list = []

        try:
            alt_resp = requests.get(alt_search_url, headers=alt_search_headers, params=alt_search_params, timeout=20)
            alt_resp.raise_for_status()
            all_books = alt_resp.json().get('books', [])
            alt_data_list = [b for b in all_books if b.get('format', '').lower() in ['pdf', 'epub']]
        except requests.exceptions.RequestException as e:
            final_flash_message = f'Error connecting to API while searching for alternatives: {e}'
            return final_flash_message, final_flash_category, None

        if not alt_data_list:
            final_flash_message = f"Original version failed ({result_message}). No PDF or EPUB alternatives found."
            final_flash_category = "warning"
            return final_flash_message, final_flash_category, None

        # --- LOGIKA PRIORYTETÓW ---
        print("--- Priority 1: Searching for same Title AND Author ---")
        for alt_item in alt_data_list:
            if alt_item.get('md5') == original_md5: continue
            if are_strings_similar(alt_item.get('title'), original_title) and \
                    are_strings_similar(alt_item.get('author'), original_author):
                print(f"Found match: {alt_item.get('title')} by {alt_item.get('author')}")

                # <<< KLUCZOWA POPRAWKA TUTAJ >>>
                # Pobieramy format z elementu alternatywnego, a nie z hardkodowanej wartości
                alt_format = alt_item.get('format', 'pdf')

                alt_s, alt_m, _ = attempt_download_and_add(
                    alt_item.get('md5'), alt_item.get('title'), alt_item.get('author'),
                    alt_item.get('year'), alt_item.get('imgUrl'), alt_format,
                    is_alternative=True, original_md5=original_md5
                )
                if alt_s is True:
                    final_flash_message = f'Original version failed. Added an alternative version: "{alt_m}".'
                    final_flash_category = "success"
                    alternative_added = True
                    break

        if not alternative_added:
            print("--- Priority 2: Searching for same Title ---")
            for alt_item in alt_data_list:
                if alt_item.get('md5') == original_md5: continue
                if are_strings_similar(alt_item.get('title'), original_title):
                    print(f"Found match: {alt_item.get('title')}")

                    # <<< KLUCZOWA POPRAWKA TUTAJ >>>
                    alt_format = alt_item.get('format', 'pdf')

                    alt_s, alt_m, _ = attempt_download_and_add(
                        alt_item.get('md5'), alt_item.get('title'), alt_item.get('author'),
                        alt_item.get('year'), alt_item.get('imgUrl'), alt_format,
                        is_alternative=True, original_md5=original_md5
                    )
                    if alt_s is True:
                        final_flash_message = f'Original version failed. Added an alternative version with the same title: "{alt_m}".'
                        final_flash_category = "success"
                        alternative_added = True
                        break

        if not alternative_added:
            final_flash_message = f"Original version failed ({result_message}). Could not find or download a working alternative."
            final_flash_category = "danger"

    else:
        final_flash_message = f"Failed to add book due to an unexpected error: {result_message}"
        final_flash_category = "danger"

    return final_flash_message, final_flash_category, final_file_path