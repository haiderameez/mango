"""The Mango console: one static page, served by the application that backs it.

The page authenticates against the ordinary `/auth` endpoints and carries a bearer token
like any other client, so the console has no privileged path into the API.
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["console"])

CONSOLE_PAGE = Path(__file__).resolve().parents[1] / "static" / "console.html"


@router.get("/console", include_in_schema=False)
def console_page():
    return FileResponse(CONSOLE_PAGE, media_type="text/html")
