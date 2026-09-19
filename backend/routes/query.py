from fastapi import APIRouter, Response

from backend import events, service, stub
from backend.config import get_settings
from backend.contract import ApiError, QueryRequest, Turn

router = APIRouter(prefix="/api", tags=["query"])


@router.post("/query", response_model=Turn, responses={422: {"model": ApiError}})
def query(req: QueryRequest) -> Turn:
    if get_settings().stub_mode:
        return stub.query(req.text, req.channel)
    return service.answer(req.text, req.channel, req.discreet)


@router.get(
    "/turns/latest",
    response_model=Turn,
    responses={204: {"description": "No turns yet"}},
)
def latest_turn() -> Turn | Response:
    turn = events.latest_turn()
    return turn if turn else Response(status_code=204)
