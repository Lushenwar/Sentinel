import jwt

from app import settings

_ALGORITHMS = ["RS256"]


def verify_token(token: str, public_key: str) -> dict:
    return jwt.decode(
        token,
        public_key,
        algorithms=_ALGORITHMS,
        audience=settings.get("auth", "audience"),
        issuer=settings.get("auth", "issuer"),
        leeway=settings.get("auth", "leeway_s"),
    )


def current_user_id(headers: dict, public_key: str) -> str:
    scheme, _, token = headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise PermissionError("missing bearer token")
    return verify_token(token, public_key)["sub"]
