from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from backend.contract import ApiError, DatasetInfo
from backend.errors import not_implemented

router = APIRouter(prefix="/api/dataset", tags=["dataset"])


@router.get("", response_model=DatasetInfo)
def get_dataset() -> DatasetInfo:
    raise not_implemented("dataset")


@router.post("/upload", response_model=DatasetInfo, responses={422: {"model": ApiError}})
async def upload_dataset(file: Annotated[UploadFile, File()]) -> DatasetInfo:
    raise not_implemented("dataset upload")


@router.post("/reset", response_model=DatasetInfo)
def reset_dataset() -> DatasetInfo:
    raise not_implemented("dataset reset")
