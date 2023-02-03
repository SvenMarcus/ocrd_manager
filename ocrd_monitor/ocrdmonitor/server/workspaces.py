from pathlib import Path
import uuid

from fastapi import APIRouter, Cookie, Request, Response, WebSocket
from fastapi.templating import Jinja2Templates
from requests.exceptions import ConnectionError
from websockets.typing import Subprotocol

import ocrdbrowser
import ocrdmonitor.server.proxy as proxy
from ocrdbrowser import OcrdBrowserFactory, OcrdBrowser, workspace
from ocrdmonitor.server.redirect import RedirectMap


def create_workspaces(
    templates: Jinja2Templates, factory: OcrdBrowserFactory, workspace_dir: Path
) -> APIRouter:

    router = APIRouter(prefix="/workspaces")

    running_browsers: set[OcrdBrowser] = set()
    redirects = RedirectMap()

    @router.get("/", name="workspaces.list")
    def list_workspaces(request: Request) -> Response:
        spaces = [
            Path(space).relative_to(workspace_dir)
            for space in workspace.list_all(workspace_dir)
        ]

        return templates.TemplateResponse(
            "list_workspaces.html.j2",
            {"request": request, "workspaces": spaces},
        )

    @router.get("/open/{workspace:path}", name="workspaces.open")
    def open_workspace(request: Request, workspace: str) -> Response:
        workspace_path = workspace_dir / workspace

        session_id = request.cookies.setdefault("session_id", str(uuid.uuid4()))
        response = templates.TemplateResponse(
            "workspace.html.j2",
            {"request": request, "workspace": workspace},
        )
        response.set_cookie("session_id", session_id)

        browser = _launch_browser(session_id, workspace_path)
        redirects.add(session_id, Path(workspace), browser)

        return response

    # NOTE: It is important that the route path here ends with a slash, otherwise
    #       the reverse routing will not work as broadway.js uses window.location
    #       which points to the last component with a trailing slash.
    @router.get("/view/{workspace:path}/", name="workspaces.view")
    def workspace_reverse_proxy(
        request: Request, workspace: str, session_id: str = Cookie(default=None)
    ) -> Response:
        workspace_path = Path(workspace)
        redirect = redirects.get(session_id, workspace_path)
        try:
            return proxy.forward(redirect, str(workspace_path))
        except ConnectionError:
            return templates.TemplateResponse(
                "view_workspace_failed.html.j2",
                {"request": request, "workspace": workspace},
            )

    @router.websocket("/view/{workspace:path}/socket", name="workspaces.view.socket")
    async def workspace_socket_proxy(
        websocket: WebSocket, workspace: Path, session_id: str = Cookie(default=None)
    ) -> None:
        redirect = redirects.get(session_id, workspace)
        url = redirect.redirect_url(str(workspace / "socket"))
        await websocket.accept(subprotocol="broadway")

        async with proxy.WebSocketAdapter(
            url, [Subprotocol("broadway")]
        ) as broadway_socket:
            while True:
                await proxy.tunnel(broadway_socket, websocket)

    def _launch_browser(session_id: str, workspace: Path) -> OcrdBrowser:
        browser = ocrdbrowser.launch(
            str(workspace),
            session_id,
            factory,
            running_browsers,
        )

        running_browsers.add(browser)
        return browser

    return router