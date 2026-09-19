from fastapi import APIRouter, Response

from backend import events
from backend.contract import ApiError, QueryRequest, Turn
from backend.errors import not_implemented

router = APIRouter(prefix="/api", tags=["query"])


@router.post("/query", response_model=Turn, responses={422: {"model": ApiError}})
def query(req: QueryRequest) -> Turn:
    raise not_implemented("query")


@router.get(
    "/turns/latest",
    response_model=Turn,
    responses={204: {"description": "No turns yet"}},
)
def latest_turn() -> Turn | Response:
    turn = events.latest_turn()
    return turn if turn else Response(status_code=204)
