from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from backend import events, service, state, stub
from backend.analysis.loader import CsvError
from backend.config import get_settings
from backend.contract import ApiError, DatasetInfo, ErrorCode
from backend.errors import ApiException

router = APIRouter(prefix="/api/dataset", tags=["dataset"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _changed(info: DatasetInfo) -> DatasetInfo:
    events.publish_dataset(info)
    service.warm_async()
    return info


@router.get("", response_model=DatasetInfo)
def get_dataset() -> DatasetInfo:
    if get_settings().stub_mode:
        return stub.dataset()
    return state.ledger().info


@router.post("/upload", response_model=DatasetInfo, responses={422: {"model": ApiError}})
async def upload_dataset(file: Annotated[UploadFile, File()]) -> DatasetInfo:
    if get_settings().stub_mode:
        return stub.uploaded_dataset(file.filename or "upload.csv")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ApiException(422, ErrorCode.csv_invalid, "The file is larger than 5 MB")
    try:
        info = state.load_upload(raw, file.filename or "upload.csv")
    except CsvError as exc:
        raise ApiException(422, ErrorCode.csv_invalid, str(exc), exc.details) from exc
    return _changed(info)


@router.post("/reset", response_model=DatasetInfo)
def reset_dataset() -> DatasetInfo:
    if get_settings().stub_mode:
        return stub.reset_dataset()
    return _changed(state.load_default())
