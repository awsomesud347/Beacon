from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from backend import stub
from backend.config import get_settings
from backend.contract import ApiError, DatasetInfo
from backend.errors import not_implemented

router = APIRouter(prefix="/api/dataset", tags=["dataset"])


@router.get("", response_model=DatasetInfo)
def get_dataset() -> DatasetInfo:
    if get_settings().stub_mode:
        return stub.dataset()
    raise not_implemented("dataset")


@router.post("/upload", response_model=DatasetInfo, responses={422: {"model": ApiError}})
async def upload_dataset(file: Annotated[UploadFile, File()]) -> DatasetInfo:
    if get_settings().stub_mode:
        return stub.uploaded_dataset(file.filename or "upload.csv")
    raise not_implemented("dataset upload")


@router.post("/reset", response_model=DatasetInfo)
def reset_dataset() -> DatasetInfo:
    if get_settings().stub_mode:
        return stub.reset_dataset()
    raise not_implemented("dataset reset")
