# app.py

import os
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import traceback

# --- Librosa/Audio Imports ---
import librosa
import numpy as np
import requests as req_lib
import io
# --- End Librosa/Audio Imports ---

load_dotenv()
app = Flask(__name__)

# --- Gemini API Configuration ---
try:
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        print("ERROR: GEMINI_API_KEY not found.")
        gemini_llm = None
    else:
        genai.configure(api_key=gemini_api_key)
        gemini_model_name = 'models/gemini-1.5-flash-latest'
        gemini_llm = genai.GenerativeModel(gemini_model_name)
        print(f"Gemini API configured successfully with model: {gemini_model_name}")
except Exception as e:
    print(f"FATAL ERROR configuring Gemini: {e}")
    traceback.print_exc()
    gemini_llm = None
# --- End Gemini Config ---

# --- Text-based Genre Identification Function ---
def get_music_genre(song_title, artist_name):
    if not gemini_llm: return "Error: Text-based genre API not configured."
    if not song_title or not artist_name: return "Please provide both song title and artist name."

    prompt = f'You are a music expert. For the song "{song_title}" by "{artist_name}", identify its specific music genre and sub-genre. Provide a concise answer in title case. Examples: Tech House, Progressive Rock. Do not add conversational fluff.'
    try:
        print(f"DEBUG: Sending text prompt for: {song_title}")
        response = gemini_llm.generate_content(prompt)
        cleaned_genre = response.text.strip().replace("*", "").replace("`", "")
        print(f"DEBUG (Text): Cleaned genre: '{cleaned_genre}'")
        return cleaned_genre if cleaned_genre else "Could not determine genre."
    except Exception as e:
        print(f"ERROR in get_music_genre: {e}")
        return f"Error communicating with Gemini API (text): {str(e)}"

# --- Audio Feature Extraction ---
def describe_audio_features(y, sr):
    features = []
    try:
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        features.append(f"Tempo: {tempo:.2f} BPM.")
    except Exception: pass
    try:
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        features.append(f"Brightness (spectral centroid): {np.mean(centroid):.2f}.")
    except Exception: pass
    try:
        contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        features.append(f"Textural richness (spectral contrast): {np.mean(contrast):.2f}.")
    except Exception: pass
    return " ".join(features) if features else "Could not extract audio features."

# --- Flask Routes ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        song_title = request.form.get('song_title', '').strip()
        artist_name = request.form.get('artist_name', '').strip()
        genre_result = get_music_genre(song_title, artist_name)
        return render_template('index.html', genre_result=genre_result, song_title_input=song_title, artist_name_input=artist_name)
    return render_template('index.html')

@app.route('/search_streaming', methods=['POST'])
def search_streaming():
    data = request.get_json()
    song_title, artist_name = data.get('song_title'), data.get('artist_name')
    if not song_title or not artist_name:
        return jsonify({"error": "Song title and artist name are required"}), 400

    query = f'artist:"{artist_name}" track:"{song_title}"'
    try:
        response = req_lib.get("https://api.deezer.com/search/track", params={'q': query, 'limit': 10}, timeout=10)
        response.raise_for_status()
        results = response.json()
        tracks = [{k: item.get(k) for k in ['id', 'title_short', 'preview']} for item in results.get('data', []) if item.get('preview')]
        for track, item in zip(tracks, results.get('data', [])):
            track['name'] = item.get('title_short')
            track['artist'] = item.get('artist', {}).get('name')
            track['image_url'] = item.get('album', {}).get('cover_medium')
            track['preview_url'] = item.get('preview')
        print(f"DEBUG: Found {len(tracks)} tracks with previews.")
        return jsonify(tracks)
    except Exception as e:
        print(f"DEEZER SEARCH ERROR: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/analyze_audio_genre', methods=['POST'])
def analyze_audio_genre():
    if not gemini_llm: return jsonify({"error": "Genre analysis API not configured"}), 503
    data = request.get_json()
    preview_url, song_title, artist_name = data.get('preview_url'), data.get('song_title'), data.get('artist_name')
    if not preview_url: return jsonify({"error": "Preview URL is required"}), 400

    try:
        audio_response = req_lib.get(preview_url, timeout=15)
        audio_response.raise_for_status()
        
        audio_stream = io.BytesIO(audio_response.content)

        # ✨ MODIFIED: Added mono=True and sr=22050 to reduce memory usage
        y, sr = librosa.load(audio_stream, mono=True, sr=22050, duration=30)
        
        feature_description = describe_audio_features(y, sr)
        print(f"DEBUG: Audio features: {feature_description}")

        if "Could not extract" in feature_description:
            return jsonify({"genre_by_audio": "Could not analyze audio."})

        prompt = f'You are a music expert. Based on this audio analysis for "{song_title}" by "{artist_name}", identify the specific genre: {feature_description}. Provide a concise, expert answer in title case.'
        
        response = gemini_llm.generate_content(prompt)
        cleaned_genre = response.text.strip().replace("*", "").replace("`", "")
        print(f"DEBUG (Audio): Cleaned genre: '{cleaned_genre}'")
        
        return jsonify({"genre_by_audio": cleaned_genre if cleaned_genre else "Could not determine genre."})

    except Exception as e:
        print(f"Error during audio analysis: {e}")
        traceback.print_exc()
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)