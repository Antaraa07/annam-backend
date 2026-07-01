from pydantic import BaseModel


class UploadResponse(BaseModel):
    image_id: str
    filename: str
    status: str