import json
import os
import requests

from flask import current_app
from flask_login import current_user
from app import db
from models import Book, UserBook
from utils.string_utils import are_strings_similar, sanitize_filename


def get_pdf_folder():
    folder = os.path.join(current_app.instance_path, 'pdfs')
    os.makedirs(folder, exist_ok=True)
    return folder


def attempt_download_and_add(book_md5, book_title, book_author, book_year_str, book_cover_url,
                             book_file_format, is_alternative=False, original_md5=None):
    pdf_full_path_final = None

    # Check if version already exists
    existing_version = Book.query.filter_by(md5=book_md5).first()
    if existing_version:
        if is_alternative:
            print(f"Alternative MD5 {book_md5} ('{book_title}') already exists in DB. Skipping download.")
            return False, "Alternative version already exists."

    year_p = int(book_year_str) if book_year_str and str(book_year_str).isdigit() else None

    get_links_url = "https://annas-archive-api.p.rapidapi.com/download"
    get_links_params = {"md5": book_md5}
    api_headers = {
        "X-RapidAPI-Key": current_app.config['RAPIDAPI_KEY'],
        "X-RapidAPI-Host": "annas-archive-api.p.rapidapi.com"
    }

    pdf_folder = get_pdf_folder()
    current_pdf_fname = f"{sanitize_filename(book_title)}_{book_md5}.{book_file_format}"
    current_pdf_full_path = os.path.join(pdf_folder, current_pdf_fname)

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
            print(f"Attempting PDF from link {i + 1}/{len(dl_links)}: {actual_link} for '{book_title}'")
            try:
                pdf_dl_h = {'User-Agent': 'Mozilla/5.0...'}
                pdf_r = requests.get(actual_link, stream=True, timeout=180, headers=pdf_dl_h, allow_redirects=True)
                print(f"PDF download status from {actual_link}: {pdf_r.status_code}")
                pdf_r.raise_for_status()

                pdf_type = pdf_r.headers.get('Content-Type', '').lower()
                pdf_disp = pdf_r.headers.get('Content-Disposition', '')
                is_pdf = False

                if 'application/pdf' in pdf_type:
                    is_pdf = True
                elif 'application/octet-stream' in pdf_type:
                    if '.pdf' in pdf_disp.lower():
                        is_pdf = True
                    else:
                        first_b = next(pdf_r.iter_content(4, decode_unicode=False), b'')
                        if first_b == b'%PDF':
                            is_pdf = True
                            with open(current_pdf_full_path, 'wb') as f:
                                f.write(first_b)
                                for chunk in pdf_r.iter_content(8192):
                                    f.write(chunk)
                            downloaded_successfully = True
                            break
                        else:
                            print(f"Octet-stream not PDF: {first_b}")

                if is_pdf and not downloaded_successfully:
                    with open(current_pdf_full_path, 'wb') as f:
                        for chunk in pdf_r.iter_content(8192):
                            f.write(chunk)
                    downloaded_successfully = True
                    break
                elif not is_pdf:
                    last_err_msg_dl = f"Link {i + 1} not PDF (type: {pdf_type})."

            except requests.exceptions.RequestException as e_d:
                print(f"Error with link {i + 1} for '{book_title}': {e_d}")
                last_err_msg_dl = f"Error with link {i + 1}: {e_d}"

            if downloaded_successfully:
                break

        if not downloaded_successfully:
            return False, last_err_msg_dl

        pdf_full_path_final = current_pdf_full_path
        print(f"File for '{book_title}' saved: {pdf_full_path_final}, Size: {os.path.getsize(pdf_full_path_final)}")

        # Create the main book entry
        new_book_obj = Book(
            title=book_title,
            author=book_author,
            year_published=year_p,
            cover_url=book_cover_url,
            md5=book_md5,
            pdf_path=pdf_full_path_final,
            file_format=book_file_format
        )
        db.session.add(new_book_obj)
        db.session.flush()  # Save to get ID

        # Add to user collection
        user_book = UserBook(
            user_id=current_user.id,
            book_id=new_book_obj.id,
            status=0
        )
        db.session.add(user_book)
        db.session.commit()

        return True, book_title, pdf_full_path_final

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
                return "member_required", "Original book requires membership."

        err_msg += f" Response: {api_err_msg_to_check[:100]}"
        print(err_msg)
        return False, "Alternative version already exists.", None


def try_add_original_or_alternatives(original_title, original_author, original_year_str, original_cover_url,
                                     original_md5, original_file_format, original_search_query, user):

    success_status, result_message, _ = attempt_download_and_add(
        original_md5, original_title, original_author, original_year_str, original_cover_url, original_file_format
    )

    final_flash_message = ""
    final_flash_category = "danger"
    pdf_full_path_final = None

    if success_status is True:
        final_flash_message = f'Book "{result_message}" added to your collection!'
        final_flash_category = "success"
        # Use get_pdf_folder() here as well
        pdf_full_path_final = os.path.join(get_pdf_folder(), f"{original_title}_{original_md5}.pdf")

    elif success_status == "member_required":
        print(f"Original MD5 {original_md5} requires membership. Searching for alternatives for query: '{original_search_query}'")
        alt_search_url = "https://annas-archive-api.p.rapidapi.com/search"
        alt_search_params = {"q": original_search_query, "ext": "pdf", "limit": "10", "sort": "most_relevant"}
        alt_search_headers = {
            "X-RapidAPI-Key": current_app.config['RAPIDAPI_KEY'],
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
                        alt_item.get('year'), alt_item.get('imgUrl'), alt_item.get('format', 'pdf'),
                        is_alternative=True
                    )
                    if alt_s is True:
                        final_flash_message = f'The selected version required membership. Added a similar available version: "{alt_m}".'
                        final_flash_category = "success"
                        alternative_added = True
                        break

            # Priority 2: Similar author
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
                            final_flash_message = f'The selected version required membership. Added a version by the same author: "{alt_m}".'
                            final_flash_category = "success"
                            alternative_added = True
                            break

            # Priority 3: Any alternative version
            if not alternative_added:
                for alt_item in alt_data_list:
                    if alt_item.get('md5') == original_md5:
                        continue
                    alt_s, alt_m = attempt_download_and_add(
                        alt_item.get('md5'), alt_item.get('title'), alt_item.get('author'),
                        alt_item.get('year'), alt_item.get('imgUrl'), alt_item.get('format', 'pdf'),
                        is_alternative=True
                    )
                    if alt_s is True:
                        final_flash_message = f'The selected version required membership. Added an alternative version: "{alt_m}".'
                        final_flash_category = "success"
                        alternative_added = True
                        break

            if not alternative_added:
                final_flash_message = 'All alternative versions failed or are unavailable.'
                final_flash_category = "danger"

        except requests.exceptions.RequestException as e:
            final_flash_message = f'Error while searching for alternatives: {e}'
            final_flash_category = "danger"

    else:
        final_flash_message = f"Failed to add book: {result_message}"
        final_flash_category = "danger"

    return final_flash_message, final_flash_category, pdf_full_path_final
