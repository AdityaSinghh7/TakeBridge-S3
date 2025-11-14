from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from pathlib import Path


def ensure_test_stubs() -> None:
    """Install lightweight stand-ins for optional dependencies absent in tests."""

    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    if "mcp" not in sys.modules:
        mcp_module = types.ModuleType("mcp")

        class _StubClientSession:  # pragma: no cover
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def initialize(self):
                return None

        mcp_module.ClientSession = _StubClientSession
        sys.modules["mcp"] = mcp_module

        client_module = types.ModuleType("mcp.client")
        stream_module = types.ModuleType("mcp.client.streamable_http")

        async def _streamablehttp_client(*args, **kwargs):  # pragma: no cover
            raise RuntimeError("streamablehttp_client stub")

        stream_module.streamablehttp_client = _streamablehttp_client
        client_module.streamable_http = stream_module
        sys.modules["mcp.client"] = client_module
        sys.modules["mcp.client.streamable_http"] = stream_module

    if "requests" not in sys.modules:

        requests_module = types.ModuleType("requests")

        class _StubResponse:  # pragma: no cover
            status_code = 200
            text = ""
            headers: dict[str, str] = {}

            def json(self):
                return {}

        def _stubbed_request(*args, **kwargs):  # pragma: no cover
            raise RuntimeError("requests stub")

        requests_module.Response = _StubResponse
        requests_module.get = _stubbed_request
        requests_module.post = _stubbed_request
        requests_module.put = _stubbed_request
        sys.modules["requests"] = requests_module

    if "sqlalchemy" not in sys.modules:
        sqlalchemy_module = types.ModuleType("sqlalchemy")

        class _StubEngine:  # pragma: no cover
            pass

        def _create_engine(*args, **kwargs):  # pragma: no cover
            return _StubEngine()

        def _select(*args, **kwargs):  # pragma: no cover
            return ("select", args, kwargs)

        def _update(*args, **kwargs):  # pragma: no cover
            return ("update", args, kwargs)

        def _insert(*args, **kwargs):  # pragma: no cover
            return ("insert", args, kwargs)

        sqlalchemy_module.create_engine = _create_engine
        sqlalchemy_module.select = _select
        sqlalchemy_module.update = _update
        sqlalchemy_module.insert = _insert
        sys.modules["sqlalchemy"] = sqlalchemy_module

        orm_module = types.ModuleType("sqlalchemy.orm")

        class _StubSession:
            def commit(self):
                return None

            def rollback(self):
                return None

            def close(self):
                return None

        def _sessionmaker(*args, **kwargs):  # pragma: no cover
            def _factory():
                return _StubSession()

            return _factory

        orm_module.sessionmaker = _sessionmaker
        orm_module.Session = _StubSession
        sys.modules["sqlalchemy.orm"] = orm_module

        dialects_module = types.ModuleType("sqlalchemy.dialects")
        sqlite_module = types.ModuleType("sqlalchemy.dialects.sqlite")
        sqlite_module.insert = _insert
        dialects_module.sqlite = sqlite_module
        postgres_module = types.ModuleType("sqlalchemy.dialects.postgresql")
        postgres_module.insert = _insert
        dialects_module.postgresql = postgres_module
        sys.modules["sqlalchemy.dialects"] = dialects_module
        sys.modules["sqlalchemy.dialects.sqlite"] = sqlite_module
        sys.modules["sqlalchemy.dialects.postgresql"] = postgres_module

    if "shared.db.engine" not in sys.modules:
        engine_module = types.ModuleType("shared.db.engine")

        class _StubDBSession:  # pragma: no cover
            def commit(self):
                return None

            def rollback(self):
                return None

            def close(self):
                return None

        @contextmanager
        def _session_scope():  # pragma: no cover
            yield _StubDBSession()

        engine_module.session_scope = _session_scope
        sys.modules["shared.db.engine"] = engine_module

    if "shared.db.crud" not in sys.modules:
        crud_module = types.ModuleType("shared.db.crud")

        def _return_false(*args, **kwargs):
            return False

        def _return_none(*args, **kwargs):
            return None

        def _return_tuple(*args, **kwargs):
            return None, None

        def _return_context(*args, **kwargs):
            return None, None, None, {}

        crud_module.is_authorized = _return_false
        crud_module.get_active_mcp_for_provider = _return_tuple
        crud_module.get_active_context_for_provider = _return_context
        crud_module.upsert_user = _return_none
        crud_module.upsert_auth_config = _return_none
        crud_module.upsert_connected_account = _return_none
        crud_module.upsert_mcp_connection = _return_none
        crud_module.disconnect_account = _return_none
        crud_module.disconnect_provider = _return_none
        sys.modules["shared.db.crud"] = crud_module
