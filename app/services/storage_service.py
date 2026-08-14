from __future__ import annotations


ALLOWED_RESOURCE_TYPES = {"pdf", "source_code", "document", "image", "link", "zip"}


class StorageService:
    def validate_resource_reference(self, name: str, file_url: str, file_type: str) -> dict:
        errors: dict[str, str] = {}
        cleaned_type = file_type.strip().lower()

        if not name.strip():
            errors["name"] = "Resource name is required."
        if not file_url.strip():
            errors["file_url"] = "Resource URL is required."
        if cleaned_type not in ALLOWED_RESOURCE_TYPES:
            errors["file_type"] = "Unsupported resource type."

        return errors


storage_service = StorageService()
