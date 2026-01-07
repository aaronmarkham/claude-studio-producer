"""
Local Filesystem Storage Provider

Pricing: Free (local storage)

Features:
- Simple file operations
- No external dependencies
- Fast access for development
- Automatic directory creation

Use case: Development and testing
"""

from typing import Dict, Any, Optional
from pathlib import Path
from ..base import StorageProvider, StorageProviderConfig, StorageResult


class LocalStorageProvider(StorageProvider):
    """Local filesystem storage provider"""

    def __init__(self, config: StorageProviderConfig):
        """
        Initialize local storage provider.

        Args:
            config: Storage configuration with base_path
        """
        super().__init__(config)
        self.base_path = Path(config.base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "local"

    async def upload_file(
        self,
        local_path: str,
        remote_path: str,
        **kwargs
    ) -> StorageResult:
        """Upload file to local storage"""
        raise NotImplementedError("LocalStorageProvider.upload_file() not yet implemented")

    async def download_file(
        self,
        remote_path: str,
        local_path: str,
        **kwargs
    ) -> StorageResult:
        """Download file from local storage"""
        raise NotImplementedError("LocalStorageProvider.download_file() not yet implemented")

    async def get_url(
        self,
        remote_path: str,
        expires_in: int = 3600,
        **kwargs
    ) -> str:
        """
        Get file URL (file:// protocol).

        Args:
            remote_path: Path relative to base_path
            expires_in: Ignored for local storage

        Returns:
            file:// URL
        """
        full_path = (self.base_path / remote_path).absolute()
        return f"file://{full_path}"

    async def delete_file(self, remote_path: str, **kwargs) -> bool:
        """Delete file from local storage"""
        raise NotImplementedError("LocalStorageProvider.delete_file() not yet implemented")
