# Migrator: de Spotify a YouTube

Es una mini aplicación en Python que coge una playlist de Spotify y me la copia a YouTube, canción por canción.

## Por qué la hice

En Spotify suelen tumbar ciertas canciones, y a mí no me gusta la sensación de ir a poner mi canción favorita y no encontrarla. Necesito flexibilidad a la hora de escuchar mi música, así que di con esta alternativa: si una canción desaparece de un sitio, la tengo en el otro.

## Qué hace

- Lee una playlist de Spotify a partir de su enlace.
- Busca cada canción en YouTube (artista más título).
- Crea una playlist privada en tu cuenta de YouTube y le va añadiendo los vídeos que encuentra.
- Al final te enseña la lista de canciones que no pudo encontrar.
- Si se acaba la cuota diaria de YouTube, guarda por dónde iba y la próxima vez continúa desde ahí.

## Lo que necesitas

- Python 3.
- Una cuenta de Spotify y una app creada en el Developer Dashboard de Spotify.
- Una cuenta de Google y un proyecto en Google Cloud con la YouTube Data API v3 activada.

## Instalación

Yo lo uso con un entorno virtual:

```
python -m venv venv
venv\Scripts\activate
pip install spotipy python-dotenv google-auth-oauthlib google-api-python-client
```

En Linux o Mac el segundo comando es `source venv/bin/activate`.

## Configuración

**Spotify.** En el Developer Dashboard crea una app y añade esta Redirect URI exactamente igual:

```
http://127.0.0.1:8888/callback
```

Después crea un archivo `.env` en la carpeta del proyecto con tus credenciales:

```
SPOTIPY_CLIENT_ID=tu_client_id
SPOTIPY_CLIENT_SECRET=tu_client_secret
```

**YouTube.** En Google Cloud crea unas credenciales OAuth de tipo aplicación de escritorio, descarga el JSON y guárdalo en la carpeta del proyecto con el nombre `client_secret.json`. Si tu proyecto está en modo de pruebas, acuérdate de añadir tu cuenta como usuario de prueba.

## Cómo se usa

```
python migrator.py
```

1. Pega el enlace de la playlist de Spotify.
2. Se abre el navegador para que autorices Spotify, y luego otra vez para autorizar YouTube.
3. Escribe el nombre que quieres para la playlist en YouTube.
4. Espera a que termine. Verás el progreso canción por canción.

## Cosas que conviene saber

- **Solo playlists tuyas o colaborativas.** Con una app de Spotify en modo desarrollo solo se puede leer el contenido de tus propias playlists o de las que compartes con alguien. En las de otros se ve el nombre, pero no las canciones.
- **La cuota de YouTube es pequeña.** Cada búsqueda gasta 100 unidades y cada canción añadida 50, y el límite diario por defecto es de 10.000. Salen unas 60 o 65 canciones al día. Si tu playlist es larga, el script se para cuando se acaba la cuota, y al ejecutarlo otra vez con el mismo enlace sigue donde se quedó. El progreso se guarda en `migrator_progress.json`.
- **El primer resultado no siempre es el bueno.** El script se queda con el primer vídeo que devuelve la búsqueda, así que a veces puede ser un directo o una versión distinta. Conviene echarle un ojo a la playlist al terminar.
- **Archivos de diagnóstico.** Por defecto se generan `dump_playlist.json` y `dump_items.json` con la respuesta cruda de Spotify. Sirven para ver qué está pasando si algo falla. Cuando ya funcione todo, puedes poner `DEBUG_DUMP = False` en el script.
- **Canciones sin aparecer.** Es posible que no se encuentre una canción, ya sea porque se borró de Spotify, es un episodio, o no está disponible por X razones, está pendiente por implementarse que el usuario reciba un listado con las canciones que no se pudieron leer inicialmente.

Este proyecto está en desarrollo, presenta muchos errores que iré corrigiendo.
