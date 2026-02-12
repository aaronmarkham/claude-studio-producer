import os
import tempfile
from pathlib import Path
from unittest import mock
from core.providers.upload.youtube import YouTubeUploader, UploadResult

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
