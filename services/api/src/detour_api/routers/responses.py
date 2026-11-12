"""Response descriptions shared by the routers (so the OpenAPI contract names the error body)."""

from typing import Any

from detour_api.models.common import ErrorBody

Responses = dict[int | str, dict[str, Any]]

AUTH: Responses = {401: {"model": ErrorBody}}
ERRORS: Responses = {
    401: {"model": ErrorBody},
    404: {"model": ErrorBody},
    409: {"model": ErrorBody},
    422: {"model": ErrorBody},
}
