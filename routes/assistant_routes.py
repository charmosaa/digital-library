# routes/assistant_routes.py

import os
from flask import Blueprint, render_template, request, flash
from flask_login import login_required
import google.generativeai as genai

assistant_bp = Blueprint('assistant', __name__)

@assistant_bp.route('/assistant', methods=['GET', 'POST'])
@login_required
def assistant():
    answer = None
    query = ""

    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        flash("AI Assistant is not configured. Missing Google API key.", "danger")
        return render_template('assistant.html', answer=None, query="")

    genai.configure(api_key=api_key)

    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        if query:
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')

                prompt_instructions = (
                    "You are a helpful, friendly library assistant. You have two modes of answering:\n\n"
                    "1.  **For recommendation requests (if the user asks you to 'recommend', 'suggest', 'give me ideas for' books):**\n"
                    "    - Start with a friendly, short opening like 'Of course! Here are a few suggestions:'.\n"
                    "    - Provide a numbered list of 3 to 5 book titles.\n"
                    "    - Format: 1. \"Book Title\" by Author\n\n"
                    "2.  **For all other factual questions (like 'who wrote a book?' or 'what year...?'):**\n"
                    "    - Be brief and to the point. Answer in 1-2 sentences maximum.\n\n"
                    "**Universal Rule:** If a question asks for information about the CURRENT moment (e.g., 'today', 'this month'), you MUST respond ONLY with: 'I cannot provide real-time information.' Do not apologize or explain further.\n\n"
                    "--- \n"
                    "User's question: "
                )

                full_prompt = prompt_instructions + query

                response = model.generate_content(full_prompt)
                answer = response.text.strip()

            except Exception as e:

                print(f"Error calling Google Gemini API: {e}")
                try:
                    if response.prompt_feedback.block_reason.name == "SAFETY":
                        answer = "My response was blocked due to safety settings. Please try rephrasing your question."
                    else:
                        flash(f"An error occurred while contacting the AI Assistant: {e}", "danger")
                        answer = "Sorry, I couldn't process your request at the moment."
                except (AttributeError, NameError):
                    flash(f"An error occurred while contacting the AI Assistant: {e}", "danger")
                    answer = "Sorry, I couldn't process your request at the moment."

    return render_template('assistant.html', answer=answer, query=query)