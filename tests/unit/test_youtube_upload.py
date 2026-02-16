import os
import tempfile
from pathlib import Path
from unittest import mock
from core.providers.upload.youtube import YouTubeUploader, UploadResult

# Existing tests...

def test_uploadresult_dataclass():
    r1 = UploadResult(success=True, video_id='abc', video_url='u', error=None)
    assert r1.success is True
    assert r1.video_id == 'abc'
    assert r1.video_url == 'u'
    assert r1.error is None

    r2 = UploadResult(success=False, error='fail')
    assert not r2.success and r2.error == 'fail'

def test_token_dir_is_created():
    with tempfile.TemporaryDirectory() as tmp:
        token_dir = Path(tmp) / 'ytokens'
        uploader = YouTubeUploader(client_secrets_path='/tmp/fake.json', token_dir=token_dir)
        assert token_dir.exists() and token_dir.is_dir()

def test_youtubeuploader_initializes():
    uploader = YouTubeUploader(client_secrets_path='/tmp/secret/fake.json', token_dir=Path('/tmp/ytokendir'))
    assert uploader.client_secrets_path == '/tmp/secret/fake.json'
    assert str(uploader.token_path).endswith('token.json')

def test_upload_returns_error_for_missing_file():
    uploader = YouTubeUploader(client_secrets_path='/tmp/fake.json')
    # Patch _get_service to avoid auth attempt
    with mock.patch.object(YouTubeUploader, '_get_service'):
        result = uploader.upload('/not/a/real/file.mp4', title='Test Video')
    assert not result.success
    assert 'not found' in result.error.lower()

# New tests for update_video_metadata

def test_update_video_metadata_success():
    uploader = YouTubeUploader(client_secrets_path='/tmp/fake.json')
    dummy_video_id = 'dummy123'
    # Mock service, .videos().list().execute() & .videos().update().execute()
    with mock.patch.object(uploader, '_get_service') as mock_get_service:
        mock_service = mock.MagicMock()
        # Simulate YouTube API list result
        mock_service.videos.return_value.list.return_value.execute.return_value = {
            "items": [{
                "id": dummy_video_id,
                "snippet": {"title": "Old title", "description": "Old desc", "tags": ["old"], "categoryId": "27"},
                "status": {"privacyStatus": "private"}
            }]
        }
        # Simulate successful update
        mock_service.videos.return_value.update.return_value.execute.return_value = {
            "id": dummy_video_id
        }
        mock_get_service.return_value = mock_service
        result = uploader.update_video_metadata(dummy_video_id, title="New title", description=None, tags=None, privacy=None, category_id=None)
        assert result.success
        assert result.video_id == dummy_video_id
        assert result.video_url == f"https://youtu.be/{dummy_video_id}"

def test_update_video_metadata_not_found():
    uploader = YouTubeUploader(client_secrets_path='/tmp/fake.json')
    dummy_video_id = 'notfound123'
    with mock.patch.object(uploader, '_get_service') as mock_get_service:
        mock_service = mock.MagicMock()
        mock_service.videos.return_value.list.return_value.execute.return_value = {"items": []}
        mock_get_service.return_value = mock_service
        result = uploader.update_video_metadata(dummy_video_id, title="Test")
        assert not result.success
        assert "not found" in result.error.lower()

def test_update_video_metadata_scope_error():
    uploader = YouTubeUploader(client_secrets_path='/tmp/fake.json')
    dummy_video_id = 'id'
    with mock.patch.object(uploader, '_get_service') as mock_get_service:
        mock_service = mock.MagicMock()
        mock_service.videos.return_value.list.return_value.execute.return_value = {
            "items": [{"id": dummy_video_id, "snippet": {}, "status": {}}]
        }
        # Simulate exception with scope error
        mock_service.videos.return_value.update.return_value.execute.side_effect = Exception("Request had insufficient permissions: 403")
        mock_get_service.return_value = mock_service
        result = uploader.update_video_metadata(dummy_video_id, title="title")
        assert not result.success
        assert "re-auth" in result.error or "insufficient" in result.error.lower()
