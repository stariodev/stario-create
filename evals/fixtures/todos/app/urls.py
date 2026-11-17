"""Every route of the app, grouped by page. Pages and tests import routes from here."""

from stario import Route

# home
HOME = Route("GET /")

# todos
TODOS = Route("GET /todos")
TODOS_LIVE = Route("GET /todos/live")
ADD_TODO = Route("POST /todos")
