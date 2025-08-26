import os
from unittest.mock import patch, Mock
import pytest

# Ensure the Gemini API is not invoked during tests
os.environ.setdefault("GEMINI_API_KEY", "test-key")

import app as app_module

app = app_module.app
req_lib = app_module.req_lib


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_search_streaming_missing_params(client):
    response = client.post("/search_streaming", json={"song_title": "Song"})
    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Song title and artist name are required for streaming search"
    }


@patch("app.req_lib.get")
def test_search_streaming_success(mock_get, client):
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "data": [
            {
                "id": 1,
                "title": "Full Title",
                "title_short": "Short Title",
                "preview": "http://example.com/preview.mp3",
                "artist": {"name": "Artist"},
                "album": {
                    "title": "Album",
                    "cover_medium": "http://example.com/image.jpg",
                },
            }
        ]
    }
    mock_get.return_value = mock_response

    response = client.post(
        "/search_streaming", json={"song_title": "Song", "artist_name": "Artist"}
    )
    assert response.status_code == 200
    assert response.get_json() == [
        {
            "id": 1,
            "name": "Short Title",
            "preview_url": "http://example.com/preview.mp3",
            "artist": "Artist",
            "album": "Album",
            "image_url": "http://example.com/image.jpg",
        }
    ]


@patch("app.req_lib.get")
def test_search_streaming_http_error(mock_get, client):
    error_response = Mock()
    error_response.status_code = 500
    error_response.reason = "Server Error"
    error_response.text = "Something went wrong"

    http_error = req_lib.exceptions.HTTPError(response=error_response)

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = http_error
    mock_get.return_value = mock_response

    response = client.post(
        "/search_streaming", json={"song_title": "Song", "artist_name": "Artist"}
    )
    assert response.status_code == 500
    assert response.get_json() == {
        "error": "Error searching on Deezer (HTTP 500): Server Error"
    }
