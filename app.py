# app.py

import os
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import traceback

# --- Librosa/Audio Imports ---
import librosa
import numpy as np
import requests as req_lib # Using an alias to avoid conflict with flask.request
import io
import tempfile # For temporary file handling
# --- End Librosa/Audio Imports ---

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
        gemini_model_name = 'models/gemini-2.0-flash' # Your chosen Gemini model
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
        response = gemini_llm.generate_content(prompt)
        
        genre_text = ""
        if hasattr(response, 'text') and response.text:
            genre_text = response.text
        elif response.candidates and \
             response.candidates[0].content and \
             response.candidates[0].content.parts and \
             response.candidates[0].content.parts[0].text:
            genre_text = response.candidates[0].content.parts[0].text
        else:
            print(f"DEBUG: Could not extract text using common attributes. Full response: {response}")
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback and response.prompt_feedback.block_reason:
                return f"Blocked by API (Text): {response.prompt_feedback.block_reason_message or response.prompt_feedback.block_reason}"
            return "Error: Failed to parse response from Gemini API (text). Check server logs."

        cleaned_genre = genre_text.strip().replace("*", "").replace("`", "")
        print(f"DEBUG (Gemini Text): Cleaned genre: '{cleaned_genre}' (Hint was: '{user_hint or 'None'}')")

        if not cleaned_genre:
            return "Could not determine genre (API returned empty or only formatting characters)."
        return cleaned_genre
    except Exception as e:
        print(f"ERROR in get_music_genre for '{song_title}' by '{artist_name}': {e}")
        traceback.print_exc()
        return f"Error communicating with Gemini API (text). (Details: {str(e)})"
# --- End Text-based Genre Identification ---

# --- Audio Feature Extraction and Description ---
def describe_audio_features(y, sr):
    description_parts = []
    # (Feature extraction code remains the same as the last version)
    # Tempo
    try:
        tempo_val, _ = librosa.beat.beat_track(y=y, sr=sr)
        if isinstance(tempo_val, (float, np.float64)): 
            description_parts.append(f"Estimated tempo: {tempo_val:.2f} BPM.")
        elif isinstance(tempo_val, np.ndarray) and tempo_val.size == 1: 
            description_parts.append(f"Estimated tempo: {tempo_val.item():.2f} BPM.")
        else:
            print(f"DEBUG: Tempo detection returned multiple candidates or unexpected type: {tempo_val}")
            description_parts.append("Tempo estimation was ambiguous.")
    except Exception as e: 
        print(f"Librosa Error (tempo): {e}")
        traceback.print_exc()
        description_parts.append("Tempo could not be reliably estimated.")

    # MFCCs
    try:
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfccs_mean = np.mean(mfccs, axis=1)
        description_parts.append(f"MFCCs (timbral texture indicator, first 3 of 13 means): {mfccs_mean[:3].round(2).tolist()}.")
    except Exception as e: 
        print(f"Librosa Error (MFCCs): {e}")
        description_parts.append("MFCCs could not be extracted.")

    # Spectral Centroid
    try:
        cent = librosa.feature.spectral_centroid(y=y, sr=sr)
        description_parts.append(f"Average spectral centroid (brightness indicator): {np.mean(cent):.2f} Hz.")
    except Exception as e: 
        print(f"Librosa Error (spectral_centroid): {e}")
        description_parts.append("Spectral centroid could not be extracted.")

    # Zero-Crossing Rate
    try:
        zcr = librosa.feature.zero_crossing_rate(y)
        description_parts.append(f"Average zero-crossing rate (percussiveness/noisiness indicator): {np.mean(zcr):.4f}.")
    except Exception as e: 
        print(f"Librosa Error (ZCR): {e}")
        description_parts.append("Zero-crossing rate could not be extracted.")

    # Spectral Bandwidth
    try:
        spec_bw = librosa.feature.spectral_bandwidth(y=y, sr=sr)
        description_parts.append(f"Average spectral bandwidth (spectrum width indicator): {np.mean(spec_bw):.2f} Hz.")
    except Exception as e:
        print(f"Librosa Error (spectral_bandwidth): {e}")
        description_parts.append("Spectral bandwidth could not be extracted.")

    # Spectral Rolloff
    try:
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)
        description_parts.append(f"Average spectral rolloff (frequency capturing 85% of energy, related to brightness/skewness): {np.mean(rolloff):.2f} Hz.")
    except Exception as e:
        print(f"Librosa Error (spectral_rolloff): {e}")
        description_parts.append("Spectral rolloff could not be extracted.")

    if not description_parts or all("could not be" in part or "ambiguous" in part for part in description_parts): 
        return "Could not extract significant audio features."
    
    return " ".join(filter(None, description_parts))
# --- End Audio Feature Extraction ---

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

@app.route('/search_streaming', methods=['POST'])
def search_streaming():
    # This function remains the same as it's just for Deezer search
    data = request.get_json()
    song_title = data.get('song_title')
    artist_name = data.get('artist_name')

    if not song_title or not artist_name:
        return jsonify({"error": "Song title and artist name are required for streaming search"}), 400

    query = f'artist:"{artist_name}" track:"{song_title}"'
    deezer_api_url = "https://api.deezer.com/search/track" 
    params = {'q': query, 'limit': 10, 'output': 'json'} 

    print(f"DEBUG: Searching Deezer with query: '{query}' at URL: {deezer_api_url}")

    try:
        response = req_lib.get(deezer_api_url, params=params, timeout=10)
        response.raise_for_status() 
        results = response.json()
        
        tracks = []
        if 'data' in results and isinstance(results['data'], list):
            for item in results['data']:
                if isinstance(item, dict) and item.get('preview'):
                    track_data = {
                        'id': item.get('id'),
                        'name': item.get('title_short', item.get('title', 'Unknown Title')),
                        'preview_url': item.get('preview'),
                        'artist': "Unknown Artist",
                        'album': "Unknown Album",
                        'image_url': None
                    }
                    artist_info = item.get('artist')
                    if isinstance(artist_info, dict):
                        track_data['artist'] = artist_info.get('name', 'Unknown Artist')
                    
                    album_info = item.get('album')
                    if isinstance(album_info, dict):
                        track_data['album'] = album_info.get('title', 'Unknown Album')
                        track_data['image_url'] = album_info.get('cover_medium')
                    
                    tracks.append(track_data)
        else:
            print(f"DEBUG: Deezer search returned no 'data' array or unexpected structure. Results: {results}")

        print(f"DEBUG: Found {len(tracks)} tracks with previews on Deezer.")
        return jsonify(tracks)
    except req_lib.exceptions.HTTPError as e:
        print(f"DEEZER SEARCH HTTP ERROR: {e.response.status_code if e.response else 'N/A'} - {e.response.text if e.response else 'No response text'}")
        traceback.print_exc()
        error_reason = e.response.reason if e.response else "Unknown HTTP Error"
        status_code = e.response.status_code if e.response else 500
        return jsonify({"error": f"Error searching on Deezer (HTTP {status_code}): {error_reason}"}), status_code
    except req_lib.exceptions.RequestException as e:
        print(f"DEEZER SEARCH REQUEST ERROR: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Error connecting to Deezer: {str(e)}"}), 500
    except ValueError as e: 
        print(f"DEEZER SEARCH JSON PARSE ERROR: {e}")
        traceback.print_exc()
        return jsonify({"error": "Error parsing response from Deezer."}), 500
    except Exception as e: 
        print(f"DEEZER SEARCH UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        return jsonify({"error": f"An unexpected error occurred during Deezer search: {str(e)}"}), 500

@app.route('/analyze_audio_genre', methods=['POST'])
def analyze_audio_genre():
    if not gemini_llm:
        return jsonify({"error": "Genre analysis not available (Gemini API for audio not configured)"}), 503

    data = request.get_json()
    preview_url = data.get('preview_url')
    song_title_for_prompt = data.get('song_title', 'the provided audio clip') 
    artist_name_for_prompt = data.get('artist_name', 'the artist')
    user_hint = data.get('user_hint', None) # Get hint from JSON payload

    if not preview_url:
        return jsonify({"error": "Preview URL is required"}), 400
    
    temp_audio_file_path = None 
    try:
        print(f"DEBUG: Downloading audio from {preview_url}")
        audio_response = req_lib.get(preview_url, timeout=15) 
        audio_response.raise_for_status()
        print(f"DEBUG: Deezer audio Content-Type: {audio_response.headers.get('Content-Type')}") 
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio_file_obj:
            temp_audio_file_obj.write(audio_response.content)
            temp_audio_file_path = temp_audio_file_obj.name 
        
        print(f"DEBUG: Audio content saved to temporary file: {temp_audio_file_path}")

        y, sr = librosa.load(temp_audio_file_path, duration=30)
            
        print(f"DEBUG: Audio loaded. Duration: {librosa.get_duration(y=y, sr=sr):.2f}s, SR: {sr}Hz")

        feature_description = describe_audio_features(y, sr)
        print(f"DEBUG: Audio feature description: {feature_description}")

        if "Could not extract significant audio features" in feature_description:
            return jsonify({"genre_by_audio": "Could not analyze audio effectively (feature extraction failed or insufficient data).", "preview_url": preview_url}), 200
        
        failed_feature_count = feature_description.count("could not be reliably estimated") + \
                               feature_description.count("could not be extracted") + \
                               feature_description.count("estimation was ambiguous")
        
        parts = feature_description.split('. ')
        successful_feature_count = 0
        for part in parts:
            if "BPM" in part or "Hz" in part or "means" in part or "rate" in part:
                 if not ("could not be" in part or "ambiguous" in part):
                    successful_feature_count +=1

        if successful_feature_count < 2 : 
             return jsonify({"genre_by_audio": f"Could not analyze audio effectively (insufficient features extracted: {successful_feature_count} successful, {failed_feature_count} failed).", "preview_url": preview_url}), 200

        hint_prompt_segment = ""
        if user_hint and user_hint.strip():
            hint_prompt_segment = f"A user-provided hint suggests the genre might be related to '{user_hint.strip()}'. Consider this hint to help interpret the audio features, especially if they are ambiguous, but prioritize the sonic characteristics evident in the features if there is a clear contradiction. For example, a high BPM might normally suggest an energetic genre, but a hint like 'half-time feel' or 'dub' could mean the perceived tempo is slower."

        audio_prompt = f"""
        You are a music expert specializing in genre identification from detailed audio features.
        Consider the interplay of all provided features to determine the specific music genre and sub-genre for THE PROVIDED AUDIO CLIP.
        {hint_prompt_segment}
        Pay attention to how features like tempo, timbral texture (MFCCs), brightness (spectral centroid, rolloff), spectrum width (spectral bandwidth), and percussiveness (zero-crossing rate) combine.
        For example, low tempo with wide spectral bandwidth and specific timbral qualities might indicate an ambient or atmospheric genre.
        A high tempo might suggest an energetic genre, but also consider if other features or hints suggest a different interpretation of that tempo (e.g., half-time feel).

        Provide a concise and accurate answer. Be specific with sub-genres if possible.
        Examples of desired output format:
        - Tropical Progressive House
        - Ambient Drone
        - Dark Moody Dubstep
        - Melodic Techno
        - Psy-Dub
        - Downtempo Psybass
        - Liquid Drum and Bass
        - Ethereal Wave
        - Classic Rock (based on features)
        - Psychedelic Trance (based on features)

        Audio Feature Description:
        "{feature_description}"

        If the features (and any hint) are highly ambiguous or truly insufficient for a specific sub-genre, provide the closest broader genre.
        If highly uncertain, state "Could not confidently determine genre from audio features."
        Do not add any conversational fluff, just the genre.

        Identified Genre from Audio:
        """
        
        print(f"DEBUG: Sending audio feature prompt to Gemini (Blind Analysis). Hint: '{user_hint or 'None'}'. Original Song: {song_title_for_prompt}, Artist: {artist_name_for_prompt}")
        gemini_response = gemini_llm.generate_content(audio_prompt)
        
        genre_text_audio = ""
        if hasattr(gemini_response, 'text') and gemini_response.text:
            genre_text_audio = gemini_response.text
        elif gemini_response.candidates and \
             response.candidates[0].content and \
             response.candidates[0].content.parts and \
             response.candidates[0].content.parts[0].text:
            genre_text_audio = response.candidates[0].content.parts[0].text # Corrected to response, not gemini_response here if using the broader response structure
        else: # Fallback or if using direct text from gemini_response
            if hasattr(gemini_response, 'candidates') and \
                gemini_response.candidates[0].content and \
                gemini_response.candidates[0].content.parts and \
                gemini_response.candidates[0].content.parts[0].text:
                genre_text_audio = gemini_response.candidates[0].content.parts[0].text
            else:
                print(f"DEBUG: Could not extract audio genre text using common attributes. Full response: {gemini_response}")
                if hasattr(gemini_response, 'prompt_feedback') and gemini_response.prompt_feedback and gemini_response.prompt_feedback.block_reason:
                    return jsonify({"genre_by_audio": f"Blocked by API (Audio): {gemini_response.prompt_feedback.block_reason_message or gemini_response.prompt_feedback.block_reason}", "preview_url": preview_url})
                return jsonify({"genre_by_audio": "Error: Failed to parse response from Gemini API (audio).", "preview_url": preview_url})


        cleaned_genre_audio = genre_text_audio.strip().replace("*", "").replace("`", "")
        print(f"DEBUG (Audio Gemini - Blind Analysis with Hint): Cleaned genre: '{cleaned_genre_audio}' (Hint was: '{user_hint or 'None'}')")

        if not cleaned_genre_audio:
            return jsonify({"genre_by_audio": "Could not determine genre from audio (API returned empty).", "preview_url": preview_url})
        
        return jsonify({"genre_by_audio": cleaned_genre_audio, "preview_url": preview_url})

    except req_lib.exceptions.HTTPError as e:
        # (Error handling remains the same)
        print(f"Error during audio processing (HTTPError for download): {e.response.status_code if e.response else 'N/A'} - {e.response.text if e.response else 'No response text'}")
        status_code = e.response.status_code if e.response else 500
        error_reason = e.response.reason if e.response else "Unknown HTTP Error during audio processing"
        return jsonify({"error": f"Failed to download/process audio preview (HTTP {status_code}): {error_reason}"}), status_code
    except req_lib.exceptions.RequestException as e:
        print(f"Error downloading audio: {e}")
        return jsonify({"error": f"Failed to download audio preview: {str(e)}"}), 500
    except librosa.LibrosaError as e: 
        print(f"Librosa error during audio processing: {e}")
        traceback.print_exc() 
        return jsonify({"error": f"Audio processing error (librosa): {str(e)}"}), 500
    except Exception as e:
        print(f"Error during audio analysis (Unexpected): {e}")
        traceback.print_exc() 
        return jsonify({"error": f"An unexpected error occurred during audio analysis: {str(e)}"}), 500
    finally:
        if temp_audio_file_path and os.path.exists(temp_audio_file_path):
            try:
                os.remove(temp_audio_file_path)
                print(f"DEBUG: Deleted temporary file: {temp_audio_file_path}")
            except Exception as e_remove:
                print(f"ERROR: Could not delete temporary file {temp_audio_file_path}: {e_remove}")
# --- End Flask Routes ---

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
