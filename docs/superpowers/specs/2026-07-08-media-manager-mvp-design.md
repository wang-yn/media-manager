# Media Manager MVP Design

## Status

- Date: 2026-07-08
- Status: Approved design, pending implementation plan
- Scope: First usable MVP for manually managing local movie and series folders

## Goals

Build the smallest useful web tool for local media organization:

- Add media libraries and mark each as `movie` or `series`.
- Show scanned media items from configured libraries.
- Parse basic metadata from file and directory names.
- Manually scrape metadata from TMDB.
- Write scraped metadata as Emby/Jellyfin-compatible `.nfo` files beside media files.
- Preview and execute directory/file renames.
- Show detailed synchronous error messages when an operation fails.

## Non-Goals

The MVP will not include:

- Background jobs.
- Automatic periodic scanning.
- Automatic scraping.
- Batch scraping.
- Subtitle download.
- Database indexing.
- Advanced filtering, sorting, or complex UI flows.
- Image/poster download.
- Full actor/crew metadata.

## Architecture

The frontend stays as a React + Vite single-page workbench.

The backend changes from `http.server` to FastAPI. FastAPI owns request parsing, validation, routing, and JSON error responses. Scanning, TMDB access, NFO generation, config writing, and rename planning stay in small plain Python modules so they can be tested without HTTP.

Persistent state stays minimal:

- Media library configuration is stored in `/config/config.toml`.
- Scraped metadata is stored as `.nfo` files beside media files.
- No database, queue, or cache index is introduced for the MVP.

The TMDB API key is read from configuration or environment, preferably `TMDB_API_KEY`. The key itself must not be committed.

## User Flows

### Add Media Library

The user enters:

- Library name.
- Library type: `movie` or `series`.
- Absolute path inside the mounted media tree.

The backend validates the path, appends the library to `/config/config.toml`, reloads config, and returns the updated library list. The UI refreshes the media list after saving.

### View Media List

The media list is produced by a synchronous scan of configured libraries.

Movie libraries treat a video file or its parent directory as one movie item. Series libraries treat the first directory under the library root as the show title and parse `SxxEyy` from file names when possible.

Rows show:

- Parsed title.
- Year if found.
- Type.
- Season and episode for series.
- File path.
- Whether an `.nfo` already exists.
- The latest operation error for that row, if any.

### Manual TMDB Scraping

The user starts scraping from one media row.

The backend searches TMDB using the parsed title, year, and media type. The UI shows candidate results instead of auto-selecting the first match. The user picks a candidate, then the backend fetches the selected TMDB details and writes `.nfo`.

Movie output:

- `movie.nfo` in the movie directory.

Series output:

- `tvshow.nfo` in the show directory.
- Episode `.nfo` beside the episode video when episode details are available.

The MVP writes only basic Emby/Jellyfin-compatible fields:

- Title.
- Original title when available.
- Year.
- Overview.
- TMDB ID.
- Media type.
- Season and episode fields for episodes.

### Rename Preview And Apply

The user requests a rename preview for one media row.

The backend calculates target paths from the existing organizer templates. It returns source path, target path, related sidecar files, and blocking conflicts. The UI only enables execution when the preview has no blocking conflict.

The user can then apply the preview. Execution is synchronous and returns changed paths or a structured error.

Rename execution covers:

- The video file.
- Same-stem subtitle files.
- Same-stem episode `.nfo` files.
- Movie directory or show directory only when it can be identified without touching unrelated parents.

## API

- `GET /api/health`
- `GET /api/libraries`
- `POST /api/libraries`
- `GET /api/media`
- `POST /api/media/{id}/metadata/search`
- `POST /api/media/{id}/metadata/apply`
- `POST /api/media/{id}/rename/preview`
- `POST /api/media/{id}/rename/apply`

Media IDs are generated from the current file path with a stable hash. Each operation rescans configured libraries and resolves the ID to a current file path. If a file has already moved, the API returns a not-found error and the UI refreshes the list.

## Error Handling

All operations are synchronous. Failures return a JSON object shaped like:

```json
{
  "error": {
    "code": "tmdb_request_failed",
    "message": "TMDB request failed",
    "detail": "HTTP 401 Unauthorized",
    "path": "/media/movies/example/movie.mkv"
  }
}
```

The frontend displays `message`, `detail`, and the related path when present. It does not replace detailed backend errors with generic copy.

Expected error codes include:

- `invalid_library_path`
- `config_write_failed`
- `media_not_found`
- `tmdb_missing_api_key`
- `tmdb_request_failed`
- `tmdb_no_candidate_selected`
- `nfo_write_failed`
- `rename_conflict`
- `rename_outside_library`
- `rename_failed`

## File Safety

Rename operations are restricted to configured library roots.

Preview checks:

- Target path remains inside the same configured library root.
- Target path does not already exist.
- The operation has no duplicate targets.
- Related sidecar files are moved only when they share the media file stem.

Apply revalidates the preview before changing files. If validation fails, no rename is attempted.

## Frontend Shape

The MVP stays a single workbench page with three sections:

- Media libraries: list and add form.
- Media list: scanned rows with parsed metadata and NFO status.
- Row actions: scrape metadata, choose TMDB candidate, preview rename, apply rename.

The UI should stay plain and operational. No landing page, no media portal design, and no complex navigation are needed.

## Testing

Backend tests cover:

- Movie and series scanning.
- Library config append.
- TMDB client behavior with fake responses.
- NFO XML generation.
- Rename preview conflict detection.
- Rename apply for video, same-stem subtitle, and same-stem NFO.
- FastAPI endpoints for the main success paths and one structured failure.

Frontend verification covers:

- TypeScript build.
- Basic rendering states for loading, error, empty media list, and media rows.

No test should call the real TMDB API.

## Implementation Notes

Use the existing project structure where possible. Keep changes focused:

- Replace the backend HTTP entrypoint with FastAPI.
- Keep scanner logic as a plain module.
- Add small modules for TMDB, NFO, config writing, and rename planning.
- Update Docker and README only for changed startup commands and dependencies.

Skipped for MVP: custom task system, database schema, provider abstraction, and UI framework. Add them only when the first real workflow proves they are needed.
