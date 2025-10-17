"""FastAPI web application."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Easy Table Tennis Event Manager")

# TODO: Configure templates and static files
# templates = Jinja2Templates(directory="templates")
# app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Home page."""
    return "<h1>Easy Table Tennis Event Manager</h1><p>Web panel coming soon...</p>"


# TODO: Implement routes:
# - GET /groups - View all groups
# - GET /groups/{group_id}/matches - View matches in a group
# - GET /standings - View standings
# - POST /matches/{match_id}/result - Enter match result
# - POST /standings/recalculate - Recalculate standings


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
