# routes/search_routes.py

from flask import Blueprint, render_template, request
from flask import Blueprint, render_template, request, flash, current_app
import requests
import json

search_bp = Blueprint('search', __name__)


@search_bp.route('/search', methods=['GET'])
def search_books():
    query = request.args.get('query', '').strip()
    books_from_api = []
    title_text = "Search Results"

    if not query:
        flash("Please enter a search query.", "info")
        return render_template('search_results.html', books=[], query=query, title_text="Search for Books")

    if not current_app.config['RAPIDAPI_KEY']:
        flash("RapidAPI key is not configured. Please contact the administrator.", "danger")
        return render_template('search_results.html', books=[], query=query, title_text=title_text)

    url = "https://annas-archive-api.p.rapidapi.com/search"
    querystring = {
        "q": query,
        "lang": "en",
        "content": "book_any",
        "ext": "pdf, epub",
        "sort": "most_relevant",
        "limit": "20"
    }
    headers = {
        "X-RapidAPI-Key": current_app.config['RAPIDAPI_KEY'],
        "X-RapidAPI-Host": "annas-archive-api.p.rapidapi.com"
    }

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=20)
        print(f"Search API response status: {response.status_code}")
        response.raise_for_status()
        data = response.json()

        api_response_items = []
        if isinstance(data, dict) and 'books' in data and isinstance(data['books'], list):
            print("API response is a dict with a 'books' list.")
            api_response_items = data['books']
        else:
            print(f"API response structure not recognized. Data: {data}")

        if api_response_items:
            found_books = False
            for item in api_response_items:
                file_format = item.get('format', '').lower()
                if file_format in ['pdf', 'epub']:
                    books_from_api.append({
                        'title': item.get('title', 'No Title'),
                        'author': item.get('author', 'No Author'),
                        'year': item.get('year'),
                        'cover_url': item.get('imgUrl'),
                        'md5': item.get('md5'),
                        'file_format': file_format
                    })
                    found_books = True

            title_text = f"Search results for '{query}'"
            if not found_books:
                flash(f"No PDF or EPUB books found for your query '{query}'.", 'info')
        else:
            flash(f"No books found in the API response for your query '{query}'.", 'info')
            title_text = f"Search results for '{query}'"

    except requests.exceptions.Timeout:
        flash("The request to Anna's Archive timed out. Please try again later.", 'danger')
    except requests.exceptions.HTTPError as e:
        flash_message = f"Error from Anna's Archive API: {e.response.status_code}."
        try:
            error_detail = e.response.json()
            flash_message += f" Message: {error_detail.get('message', e.response.text)}"
        except ValueError:
            flash_message += f" Response: {e.response.text[:200]}"
        print(f"HTTPError in search_books: {flash_message}")
        flash(flash_message, 'danger')
    except requests.exceptions.RequestException as e:
        print(f"RequestException in search_books: {e}")
        flash(f"An error occurred while communicating with Anna's Archive: {e}", 'danger')
    except json.JSONDecodeError as e:
        print(
            f"JSONDecodeError in search_books: {e}. Response text: {response.text[:500] if 'response' in locals() else 'N/A'}")
        flash("Error parsing data from Anna's Archive API. Please try again.", 'danger')
    except Exception as e:
        print(f"Unexpected error in search_books: {e}")
        flash(f"An unexpected error occurred during search: {e}", 'danger')

    return render_template('search_results.html', books=books_from_api, query=query, title_text=title_text)