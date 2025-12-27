from __future__ import annotations

import hashlib
import posixpath
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from server.api.auth import CurrentUser, get_current_user
from server.api.server import app
from server.api import routes_drive
from server.api import run_drive


@pytest.fixture
def client():
    def _override_user():
        return CurrentUser(sub="user-123", email=None, token="token")

    app.dependency_overrides[get_current_user] = _override_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class StubStorage:
    def __init__(self) -> None:
        self.list_result = {}

    def list_objects(self, *, prefix: str, delimiter: str | None = None, max_keys: int | None = None):
        return self.list_result

    def generate_presigned_put(self, key: str, *, content_type: str | None = None, expires_in: int | None = None) -> str:
        return f"https://example.com/put/{key}"

    def generate_presigned_get(self, key: str, *, expires_in: int | None = None) -> str:
        return f"https://example.com/get/{key}"

    def head_object(self, key: str):
        return {
            "ETag": '"etag123"',
            "ContentLength": 12,
            "LastModified": datetime(2025, 1, 1, tzinfo=timezone.utc),
        }

    def copy_object(self, source_key: str, destination_key: str) -> None:
        return None

    def delete_object(self, key: str) -> None:
        return None


def test_drive_list_endpoint(client, monkeypatch):
    storage = StubStorage()
    storage.list_result = {
        "CommonPrefixes": [{"Prefix": "user-123/drive/Documents/"}],
        "Contents": [
            {
                "Key": "user-123/drive/Documents/a.txt",
                "Size": 123,
                "LastModified": datetime(2025, 1, 2, tzinfo=timezone.utc),
                "ETag": '"etag456"',
            }
        ],
    }
    monkeypatch.setattr(routes_drive, "get_attachment_storage", lambda: storage)

    resp = client.get("/api/drive/list", params={"prefix": "", "delimiter": "/"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["prefix"] == ""
    items = payload["items"]
    assert {"type": "folder", "path": "Documents/", "name": "Documents"} in items
    file_item = next(item for item in items if item["type"] == "file")
    assert file_item["path"] == "Documents/a.txt"
    assert file_item["name"] == "a.txt"
    assert file_item["size"] == 123
    assert file_item["etag"] == "etag456"


def test_drive_presign_endpoints(client, monkeypatch):
    storage = StubStorage()
    monkeypatch.setattr(routes_drive, "get_attachment_storage", lambda: storage)

    upload = client.post(
        "/api/drive/request-upload",
        json={"path": "Documents/a.txt", "content_type": "text/plain"},
    )
    assert upload.status_code == 200
    assert upload.json()["r2_key"] == "user-123/drive/Documents/a.txt"

    download = client.get("/api/drive/request-download", params={"path": "Documents/a.txt"})
    assert download.status_code == 200
    payload = download.json()
    assert payload["r2_key"] == "user-123/drive/Documents/a.txt"
    assert payload["etag"] == "etag123"
    assert payload["size"] == 12


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def iter_content(self, chunk_size: int = 1):
        yield self._content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeController:
    def __init__(self, content_map, listing_map):
        self._content_map = content_map
        self._listing_map = listing_map

    def wait_for_health(self):
        return None

    def stream_file(self, path: str, timeout: int | None = None):
        return _FakeResponse(self._content_map[path])

    def list_directory(self, path: str, timeout: int | None = None):
        return {"entries": self._listing_map.get(path, [])}


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.added = []
        self.committed = False

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM workflow_run_files" in sql:
            return _FakeResult(self._rows)
        return _FakeResult([])

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        return None

    def close(self):
        return None


def test_detect_drive_changes(monkeypatch):
    baseline_same = hashlib.sha256(b"same").hexdigest()
    baseline_old = hashlib.sha256(b"old").hexdigest()

    rows = [
        {
            "id": "1",
            "user_id": "user-123",
            "drive_path": "Documents/keep.txt",
            "r2_key": "user-123/drive/Documents/keep.txt",
            "storage_key": None,
            "filename": "keep.txt",
            "checksum": baseline_same,
            "vm_path": None,
            "content_type": "text/plain",
        },
        {
            "id": "2",
            "user_id": "user-123",
            "drive_path": "Documents/change.txt",
            "r2_key": "user-123/drive/Documents/change.txt",
            "storage_key": None,
            "filename": "change.txt",
            "checksum": baseline_old,
            "vm_path": posixpath.join(run_drive.DRIVE_VM_BASE_PATH, "Documents/change.txt"),
            "content_type": "text/plain",
        },
    ]

    fake_session = _FakeSession(rows)
    monkeypatch.setattr(run_drive, "SessionLocal", lambda: fake_session)

    base_path = run_drive.DRIVE_VM_BASE_PATH
    docs_path = posixpath.join(base_path, "Documents")
    content_map = {
        posixpath.join(base_path, "Documents/keep.txt"): b"same",
        posixpath.join(base_path, "Documents/change.txt"): b"new",
        posixpath.join(base_path, "Documents/new.txt"): b"added",
    }
    listing_map = {
        base_path: [{"path": docs_path, "is_dir": True}],
        docs_path: [
            {"path": posixpath.join(docs_path, "keep.txt"), "is_dir": False},
            {"path": posixpath.join(docs_path, "change.txt"), "is_dir": False},
            {"path": posixpath.join(docs_path, "new.txt"), "is_dir": False},
        ],
    }
    monkeypatch.setattr(
        run_drive,
        "VMControllerClient",
        lambda base_url=None: _FakeController(content_map, listing_map),
    )

    changes = run_drive.detect_drive_changes("run-123", {"controller_base_url": "http://vm"})
    assert len(changes) == 2
    paths = {change["path"] for change in changes}
    assert "Documents/change.txt" in paths
    assert "Documents/new.txt" in paths
    assert fake_session.committed is True
    assert len(fake_session.added) == 3
