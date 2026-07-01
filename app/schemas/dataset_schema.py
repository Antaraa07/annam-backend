from typing import Optional

from pydantic import BaseModel


class DatasetMetadata(BaseModel):
    dataset_name: str
    owner: str
    lab: str
    version: str
    description: str
    # Optional linkage to a project. Existing metadata files may omit this field.
    project_id: Optional[str] = None

