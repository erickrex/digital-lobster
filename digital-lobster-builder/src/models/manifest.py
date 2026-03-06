from pydantic import BaseModel


class ExportManifest(BaseModel):
    export_version: str
    site_url: str
    export_date: str
    wordpress_version: str
    total_files: int
    total_size_bytes: int
    files: dict[str, int]  # category -> file count
