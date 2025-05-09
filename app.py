import os
import google.generativeai as genai
from flask import Flask, render_template, request
from dotenv import load_dotenv
import traceback # For more detailed error logging

# Load environment variables from .env file (for local development)
load_dotenv()

app = Flask(__name__)

# Configure Gemini API
try:
    api_key_env = os.environ.get("GEMINI_API_KEY")
    if not api_key_env:
        print("ERROR: GEMINI_API_KEY not found...")
        model = None
    else:
        genai.configure(api_key=api_key_env)
        # --- CHANGE THIS LINE ---
        model = genai.GenerativeModel('models/gemini-2.0-flash')
        # --- END CHANGE ---
        print("Gemini API configured successfully with model: models/gemini-2.0-flash")
except Exception as e:
    print(f"FATAL ERROR configuring Gemini: {e}")
    traceback.print_exc()
    model = None

def get_music_genre(song_title, artist_name):
    if not model:
        print("DEBUG: get_music_genre called but model is not initialized.")
        return "Error: Gemini API not configured. Check server logs (API key or configuration issue)."
    if not song_title or not artist_name:
        return "Please provide both song title and artist name."

    prompt = f"""
    You are a music expert specializing in genre identification.
    For the song "{song_title}" by artist "{artist_name}", identify its specific music genre and sub-genre.
    Provide a concise and accurate answer.
    Examples of desired output format:
    - Tropical Progressive House
    - Dark Moody Dubstep
    - Classic Rock
    - Indie Folk Pop
    - Soulful R&B
    - Melodic Techno

If you are unsure about a very specific sub-genre, try to provide the closest broader genre.
For example, if you can't pinpoint "Melodic Progressive House", "Progressive House" or even "House" would be acceptable.
If the track is extremely obscure and you have no confident genre, then you can state "Could not confidently determine genre."
Do not add any conversational fluff, just the genre.

    Song: "{song_title}"
    Artist: "{artist_name}"
    Identified Genre:
    """

    try:
        print(f"DEBUG: Sending prompt to Gemini for: Song='{song_title}', Artist='{artist_name}'")
        response = model.generate_content(prompt)
        
        genre_text = ""
        # For google-generativeai SDK v0.5.0+ and later (like your 0.8.5)
        # The text is usually in response.text for simple cases, 
        # or more robustly response.candidates[0].content.parts[0].text
        
        if hasattr(response, 'text') and response.text:
            genre_text = response.text
            print(f"DEBUG: Extracted genre from response.text: '{genre_text}'")
        elif response.candidates and \
             response.candidates[0].content and \
             response.candidates[0].content.parts and \
             response.candidates[0].content.parts[0].text:
            genre_text = response.candidates[0].content.parts[0].text
            print(f"DEBUG: Extracted genre from response.candidates[0].content.parts[0].text: '{genre_text}'")
        else:
            print("DEBUG: Could not extract text from Gemini response using common attributes. Full response object:")
            print(f"DEBUG: Response object: {response}")
            # Check for safety blocks or other issues
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                 print(f"DEBUG: Prompt Feedback: {response.prompt_feedback}")
                 if response.prompt_feedback.block_reason:
                     return f"Blocked by API: {response.prompt_feedback.block_reason_message or response.prompt_feedback.block_reason}"
            return "Error: Failed to parse response from Gemini API. Check server logs for response structure."

        # Cleanup the extracted text
        cleaned_genre = genre_text.strip().replace("*", "").replace("`", "")
        print(f"DEBUG: Cleaned genre: '{cleaned_genre}'")

        if not cleaned_genre: # If after stripping and cleaning, the genre is empty
            return "Could not determine genre (API returned empty or only formatting characters)."
        
        return cleaned_genre # Return the (potentially "Could not confidently determine...") string

    except Exception as e:
        print(f"ERROR in get_music_genre for '{song_title}' by '{artist_name}': {e}")
        traceback.print_exc() # Print full traceback to Flask console for detailed debugging
        return f"Error communicating with Gemini API. Check server logs. (Details: {str(e)})"

@app.route('/', methods=['GET', 'POST'])
def index():
    genre_result = None
    song_title_input = ""
    artist_name_input = ""

    if request.method == 'POST':
        song_title_input = request.form.get('song_title', '').strip()
        artist_name_input = request.form.get('artist_name', '').strip()
        
        if not model:
             genre_result = "Error: Gemini API not configured. API key might be missing or invalid. Check server logs."
        elif not song_title_input or not artist_name_input:
            genre_result = "Please provide both song title and artist name."
        else:
            genre_result = get_music_genre(song_title_input, artist_name_input)

    return render_template('index.html',
                           genre_result=genre_result,
                           song_title_input=song_title_input,
                           artist_name_input=artist_name_input)

if __name__ == '__main__':
    # Using 0.0.0.0 makes the server accessible on your local network, 
    # useful if running Flask in WSL and accessing from Windows browser.
    # 127.0.0.1 (localhost) is usually fine too.
    app.run(debug=True, host='0.0.0.0', port=5000)
