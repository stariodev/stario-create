from stario import Route

# login (stario-create add auth --password)
LOGIN = Route("GET /login")
SIGN_IN = Route("POST /login")
SIGNUP = Route("GET /signup")
SIGN_UP = Route("POST /signup")
LOGOUT = Route("POST /logout")
