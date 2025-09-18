# app.py

import os
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from flask import Flask, render_template, request
from dotenv import load_dotenv
import traceback

load_dotenv() # Load environment variables from .env
app = Flask(__name__)

# --- Gemini API Configuration ---
try:
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        print("ERROR: GEMINI_API_KEY not found in environment variables. Text-based AI features will be disabled.")
        gemini_llm = None
    else:
        genai.configure(api_key=gemini_api_key)
        # Use the Gemini 1.5 Pro model for improved reasoning capabilities
        gemini_model_name = 'models/gemini-1.5-pro'
        gemini_llm = genai.GenerativeModel(gemini_model_name)
        print(f"Gemini API configured successfully with model: {gemini_model_name}")
except Exception as e:
    print(f"FATAL ERROR configuring Gemini: {e}")
    traceback.print_exc()
    gemini_llm = None
# --- End Gemini Config ---

# --- Text-based Genre Identification Function ---
def get_music_genre(song_title, artist_name, user_hint=None): # Added user_hint
    if not gemini_llm:
        print("DEBUG: get_music_genre called but gemini_llm is not initialized.")
        return "Error: Text-based genre API not configured. Check server logs."
    if not song_title or not artist_name:
        return "Please provide both song title and artist name."

    hint_text = ""
    if user_hint:
        hint_text = f"The user has provided a hint that the genre might be related to: '{user_hint}'. Please consider this hint."

    prompt = f"""
    You are a music expert specializing in genre identification.
    For the song "{song_title}" by artist "{artist_name}", identify its specific music genre and sub-genre.
    {hint_text}
    Provide a concise and accurate answer.
    Examples of desired output format:
    - Tropical Progressive House
    - Dark Moody Dubstep
    - Tech House
    - Progressive Rock
    - Psy-Dub (if hint suggests something like 'psychedelic bass')

    If you are unsure about a very specific sub-genre, try to provide the closest broader genre.
    For example, if you can't pinpoint "Melodic Progressive House", "Progressive House" or even "House" would be acceptable.
    If the track is extremely obscure and you have no confident genre, then you can state "Could not confidently determine genre."
    Do not add any conversational fluff, just the genre.

    Song: "{song_title}"
    Artist: "{artist_name}"
    Identified Genre:
    """
    try:
        print(f"DEBUG: Sending text prompt to Gemini for: Song='{song_title}', Artist='{artist_name}', Hint='{user_hint or 'None'}'")
        gemini_response = gemini_llm.generate_content(prompt)

        genre_text = ""
        if hasattr(gemini_response, 'text') and gemini_response.text:
            genre_text = gemini_response.text
        elif gemini_response.candidates and \
             gemini_response.candidates[0].content and \
             gemini_response.candidates[0].content.parts and \
             gemini_response.candidates[0].content.parts[0].text:
            genre_text = gemini_response.candidates[0].content.parts[0].text
        else:
            print(f"DEBUG: Could not extract text using common attributes. Full response: {gemini_response}")
            if hasattr(gemini_response, 'prompt_feedback') and gemini_response.prompt_feedback and gemini_response.prompt_feedback.block_reason:
                return f"Blocked by API (Text): {gemini_response.prompt_feedback.block_reason_message or gemini_response.prompt_feedback.block_reason}"
            return "Error: Failed to parse response from Gemini API (text). Check server logs."

        cleaned_genre = genre_text.strip().replace("*", "").replace("`", "")
        print(f"DEBUG (Gemini Text): Cleaned genre: '{cleaned_genre}' (Hint was: '{user_hint or 'None'}')")

        if not cleaned_genre:
            return "Could not determine genre (API returned empty or only formatting characters)."
        return cleaned_genre
    except ResourceExhausted as err:
        print(f"ERROR: Gemini API quota exceeded for '{song_title}' by '{artist_name}': {err}")
        traceback.print_exc()
        return "Gemini API quota exceeded. Please try again later."
    except Exception as e:
        print(f"ERROR in get_music_genre for '{song_title}' by '{artist_name}': {e}")
        traceback.print_exc()
        return f"Error communicating with Gemini API (text). (Details: {str(e)})"
# --- End Text-based Genre Identification ---


# --- Flask Routes ---
@app.route('/', methods=['GET', 'POST'])
def index():
    genre_result = None
    song_title_input = ""
    artist_name_input = ""
    user_hint_input = "" # Initialize user_hint

    if request.method == 'POST':
        song_title_input = request.form.get('song_title', '').strip()
        artist_name_input = request.form.get('artist_name', '').strip()
        user_hint_input = request.form.get('user_hint', '').strip() # Get hint from form
        
        if not gemini_llm:
            genre_result = "Error: Text-based genre API not configured. Check server logs."
        elif not song_title_input or not artist_name_input:
            genre_result = "Please provide both song title and artist name for text-based search."
        else:
            # Pass hint to get_music_genre
            genre_result = get_music_genre(song_title_input, artist_name_input, user_hint_input) 

    return render_template('index.html',
                           genre_result=genre_result,
                           song_title_input=song_title_input,
                           artist_name_input=artist_name_input,
                           user_hint_input=user_hint_input) # Pass hint to template

# --- End Flask Routes ---

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
