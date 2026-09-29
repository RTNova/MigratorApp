import os
import re
import json
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube"]
SPOTIFY_SCOPES = "playlist-read-private playlist-read-collaborative"

DEBUG_DUMP = True                      # Guarda la respuesta cruda de Spotify en dump_*.json
PROGRESS_FILE = "migrator_progress.json"  # Permite reanudar si se acaba la cuota de YouTube


# ---------------------------------------------------------------- Spotify

def get_spotify_client():
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError(
            "Asegúrate de tener SPOTIPY_CLIENT_ID y SPOTIPY_CLIENT_SECRET en tu archivo .env"
        )

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://127.0.0.1:8888/callback",
        scope=SPOTIFY_SCOPES,
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def extract_spotify_id(url_or_id):
    match = re.search(r"playlist/([a-zA-Z0-9]+)", url_or_id)
    if match:
        return match.group(1)
    return url_or_id.strip()


def clean_track_name(title):
    return re.sub(r"\(.*?\)|\[.*?\]", "", title).strip()


def dump_json(name, data):
    if DEBUG_DUMP:
        with open(name, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def get_playlist_page(sp, playlist_id, offset):
    """
    Pide una página de elementos de la playlist.
    Prueba primero /items (nombre nuevo) y, si falla, /tracks (nombre antiguo).
    """
    last_error = None
    for endpoint in ("items", "tracks"):
        try:
            return sp._get(
                f"playlists/{playlist_id}/{endpoint}",
                limit=100,
                offset=offset,
                additional_types="track",
            )
        except SpotifyException as e:
            last_error = e
            if e.http_status in (404, 410):
                continue  # el endpoint no existe, probamos el otro
            raise
    raise last_error


def extract_track(item):
    """Soporta tanto la clave 'track' (antigua) como 'item' (nueva)."""
    if not isinstance(item, dict):
        return None
    track = item.get("track") or item.get("item")
    if not isinstance(track, dict):
        return None
    if track.get("type", "track") != "track":  # descarta podcasts/episodios
        return None
    return track


def fetch_spotify_tracks(sp, playlist_id):
    print(f"\n--- Leyendo playlist de Spotify: {playlist_id} ---")

    info = sp.playlist(playlist_id)
    dump_json("dump_playlist.json", info)
    print(f"Playlist encontrada: {info.get('name', 'Sin nombre')}")

    tracks = []
    offset = 0
    first_page = True

    while True:
        try:
            page = get_playlist_page(sp, playlist_id, offset)
        except SpotifyException as e:
            if e.http_status == 403:
                print(
                    "\n[!] Spotify devolvió 403 al leer las canciones.\n"
                    "    Las apps en Development Mode solo pueden leer el contenido de\n"
                    "    playlists propias o colaborativas. Prueba con una playlist tuya."
                )
                return tracks
            raise

        if first_page:
            dump_json("dump_items.json", page)
            print(
                f"total según Spotify: {page.get('total')} | "
                f"claves: {list(page.keys())}"
            )
            first_page = False

        items = page.get("items", [])
        if not items:
            break

        for item in items:
            track = extract_track(item)
            if not track:
                continue
            name = track.get("name")
            artists = track.get("artists") or []
            if name and artists:
                title = clean_track_name(name)
                artist = artists[0].get("name", "")
                tracks.append(
                    {"query": f"{artist} {title}", "title": title, "artist": artist}
                )

        offset += len(items)
        if not page.get("next"):
            break

    return tracks


# ---------------------------------------------------------------- YouTube

def get_youtube_client():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", YOUTUBE_SCOPES)
    credentials = flow.run_local_server(port=0)
    return build("youtube", "v3", credentials=credentials)


def search_youtube_video(youtube, query):
    response = (
        youtube.search()
        .list(part="snippet", q=query, maxResults=1, type="video")
        .execute()
    )
    items = response.get("items", [])
    return items[0]["id"]["videoId"] if items else None


def create_youtube_playlist(youtube, title, description=""):
    response = (
        youtube.playlists()
        .insert(
            part="snippet,status",
            body={
                "snippet": {"title": title, "description": description},
                "status": {"privacyStatus": "private"},
            },
        )
        .execute()
    )
    return response["id"]


def add_video_to_playlist(youtube, playlist_id, video_id):
    youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        },
    ).execute()


def is_quota_error(e):
    return isinstance(e, HttpError) and e.resp.status == 403 and b"quotaExceeded" in e.content


# ---------------------------------------------------------------- Progreso

def load_progress(spotify_id):
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get(spotify_id)
    return None


def save_progress(spotify_id, data):
    all_data = {}
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            all_data = json.load(f)
    all_data[spotify_id] = data
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- Main

def main():
    raw_input = input("Pega el enlace de Spotify: ").strip()
    spotify_id = extract_spotify_id(raw_input)

    sp = get_spotify_client()
    tracks = fetch_spotify_tracks(sp, spotify_id)
    print(f"Total canciones procesables: {len(tracks)}")

    if not tracks:
        print("No se pudieron cargar canciones. Revisa dump_items.json.")
        return

    youtube = get_youtube_client()

    progress = load_progress(spotify_id)
    if progress:
        yt_playlist_id = progress["yt_playlist_id"]
        start = progress["next_index"]
        unmatched = progress.get("unmatched", [])
        print(f"\nReanudando playlist de YouTube {yt_playlist_id} desde la canción {start + 1}")
    else:
        name = input("\nNombre para la playlist en YouTube: ").strip() or "Migrada de Spotify"
        yt_playlist_id = create_youtube_playlist(youtube, name)
        start = 0
        unmatched = []
        print(f"Playlist creada en YouTube con ID: {yt_playlist_id}\n")

    for index in range(start, len(tracks)):
        query = tracks[index]["query"]
        print(f"[{index + 1}/{len(tracks)}] Buscando: {query}...")

        try:
            video_id = search_youtube_video(youtube, query)
            if video_id:
                add_video_to_playlist(youtube, yt_playlist_id, video_id)
            else:
                print(f"  -> No encontrada: {query}")
                unmatched.append(query)
        except Exception as e:
            if is_quota_error(e):
                print(
                    "\n[!] Cuota diaria de la API de YouTube agotada.\n"
                    "    Vuelve a ejecutar el script mañana con el mismo enlace y continuará\n"
                    "    desde donde se quedó."
                )
                save_progress(
                    spotify_id,
                    {"yt_playlist_id": yt_playlist_id, "next_index": index, "unmatched": unmatched},
                )
                return
            print(f"  -> Error con '{query}': {e}")
            unmatched.append(query)

        save_progress(
            spotify_id,
            {"yt_playlist_id": yt_playlist_id, "next_index": index + 1, "unmatched": unmatched},
        )

    print("\nProceso terminado.")
    if unmatched:
        print(f"\nCanciones no encontradas ({len(unmatched)}):")
        for u in unmatched:
            print(f"- {u}")


if __name__ == "__main__":
    main()