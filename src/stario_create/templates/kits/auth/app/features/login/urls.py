from stario import Route

LOGIN = Route("GET /login")
LOGIN_START = Route("POST /login")
# The issuer sends the browser back here. Register this URL at the issuer.
LOGIN_CALLBACK = Route("GET /login/callback")
LOGOUT = Route("POST /logout")
