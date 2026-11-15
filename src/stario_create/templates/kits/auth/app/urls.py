from stario import Route

# login (stario-create add auth)
LOGIN = Route("GET /login")
LOGIN_START = Route("POST /login/{provider}")
# The provider sends the browser back here. Register this URL at each provider.
LOGIN_CALLBACK = Route("GET /login/{provider}/callback")
LOGOUT = Route("POST /logout")
