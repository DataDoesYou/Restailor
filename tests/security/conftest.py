from __future__ import annotations

import asyncio
import os
import pytest

from typing import Any, AsyncIterator, Awaitable, Callable


# Autouse guardrails for the security test package only
@pytest.fixture(autouse=True, scope="package")
def security_suite_guardrails():
    """Prevent accidental external traffic in tests/security/*.

    - Stub LLM streaming to a fast local generator.
    - Disable shared outbound httpx client factory.
    - Disable Redis pool creation and default to None for speed.
    """

    # Track originals for restoration
    originals: list[tuple[object, str, Any]] = []
    env_overrides: dict[str, str | None] = {}

    # 1) Stub LLM streaming
    try:
        import services.llm as llm

        async def _stub_stream_model(
            provider: str,
            model: str,
            system_prompt: str,
            user_prompt: str,
            params: dict[str, Any],
            timeouts: dict[str, Any],
            stop_markers: list[str] | None,
            job_id: str,
            external_cancel: Callable[[], Awaitable[bool]] | None = None,
        ) -> AsyncIterator[str]:
            # Emit a couple of tiny tokens and stop quickly
            yield "OK"
            yield "\n"
            return

        originals.append((llm, "stream_model", getattr(llm, "stream_model", None)))
        setattr(llm, "stream_model", _stub_stream_model)
    except Exception:
        pass

    # 2) Disable outbound httpx shared client
    try:
        import perf.observability as obs

        async def _no_httpx_client() -> Any:  # pragma: no cover - should never be called here
            raise RuntimeError("Outbound HTTP is disabled in security tests")

        originals.append((obs, "get_shared_async_client", getattr(obs, "get_shared_async_client", None)))
        setattr(obs, "get_shared_async_client", _no_httpx_client)
    except Exception:
        pass

    # 3) Disable Redis usage by default for speed
    env_overrides["DISABLE_REDIS"] = os.environ.get("DISABLE_REDIS")
    os.environ["DISABLE_REDIS"] = "1"
    try:
        # Make any pool creation attempts fail fast so app falls back to None
        import arq  # type: ignore

        async def _no_pool(*args, **kwargs):  # pragma: no cover
            raise RuntimeError("Redis disabled in security tests")

        originals.append((arq, "create_pool", getattr(arq, "create_pool", None)))
        setattr(arq, "create_pool", _no_pool)
    except Exception:
        pass

    # Ensure FastAPI app-level redis is None when tests import main.app
    app_prev = None
    try:
        from main import app
        app_prev = getattr(app.state, "redis", None)
        setattr(app.state, "redis", None)
    except Exception:
        pass

    # Relax strict secrets if enabled to avoid startup failures in isolated tests
    env_overrides["STRICT_SECRETS"] = os.environ.get("STRICT_SECRETS")
    os.environ["STRICT_SECRETS"] = "0"

    # Yield to tests, then restore
    try:
        yield
    finally:
        # restore patched attrs
        for mod, name, orig in originals:
            try:
                if orig is None:
                    # If missing originally, remove attr if present
                    if hasattr(mod, name):
                        delattr(mod, name)
                else:
                    setattr(mod, name, orig)
            except Exception:
                pass
        # restore app redis
        try:
            from main import app as _app
            setattr(_app.state, "redis", app_prev)
        except Exception:
            pass
        # restore env
        for k, v in env_overrides.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# Optional: provide a fake Redis that tests can opt into locally
class _FakeRedis:
    def __init__(self) -> None:
        self._kv: dict[str, Any] = {}

    async def get(self, key: str):
        return self._kv.get(key)

    async def set(self, key: str, value: Any):
        self._kv[key] = value
        return True

    async def setex(self, key: str, ttl: int, value: Any):
        self._kv[key] = value
        return True

    async def delete(self, key: str):
        self._kv.pop(key, None)
        return 1


@pytest.fixture()
def enable_fake_redis():
    """Opt-in helper for a test to enable a local fake Redis on app.state.redis."""
    from main import app
    prev = getattr(app.state, "redis", None)
    r = _FakeRedis()
    setattr(app.state, "redis", r)
    try:
        yield r
    finally:
        setattr(app.state, "redis", prev)
