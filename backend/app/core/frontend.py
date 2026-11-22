"""Serving the built dashboard (frontend/dist) from the API process.

In the container image the single-page app lives in ENVO_STATIC_DIR. Every
non-API GET that is not a real file returns index.html so client-side routes
(/projects/…, /invite/…, /cli/authorize) work on reload and from links.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

# The bundle loads only from this origin; no inline scripts. Inline style
# attributes are not needed either (React sets styles through the DOM API).
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)
HTML_HEADERS = {
    "Cache-Control": "no-cache",
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # Invitation links carry a secret token in the URL: never leak it.
    "Referrer-Policy": "no-referrer",
}


class HashedAssets(StaticFiles):
    """Vite puts a content hash in every asset name, so they never change."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def mount_frontend(app: FastAPI, static_dir: str | None) -> bool:
    """Register the dashboard routes. Must run after all API routers."""
    if not static_dir:
        return False
    root = Path(static_dir).resolve()
    index = root / "index.html"
    if not index.is_file():
        return False

    if (root / "assets").is_dir():
        app.mount("/assets", HashedAssets(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, detail="Not Found")
        if path:
            candidate = (root / path).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate, headers={"X-Content-Type-Options": "nosniff"})
        return FileResponse(index, headers=HTML_HEADERS)

    return True
