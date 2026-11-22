"""Error helpers. `detail` is always a stable machine-readable code that clients
map to user-facing messages."""

from fastapi import HTTPException, status


def unauthorized(code: str = "not_authenticated") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=code)


def forbidden(code: str = "forbidden") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail=code)


def not_found(code: str = "not_found") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=code)


def conflict(code: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail=code)


def bad_request(code: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=code)
