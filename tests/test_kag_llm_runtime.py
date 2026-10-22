import asyncio
from functools import wraps
from types import SimpleNamespace

import pytest

from uuma import kag_llm_runtime


def retry_sync(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        for attempt in range(3):
            try:
                return method(*args, **kwargs)
            except RuntimeError:
                if attempt == 2:
                    raise
    wrapped.retry = object()
    return wrapped


def retry_async(method):
    @wraps(method)
    async def wrapped(*args, **kwargs):
        for attempt in range(3):
            try:
                return await method(*args, **kwargs)
            except RuntimeError:
                if attempt == 2:
                    raise
    wrapped.retry = object()
    return wrapped


@pytest.fixture
def fake_kag(monkeypatch):
    monkeypatch.delenv("UUMA_KAG_LLM_MAX_RETRIES", raising=False)
    monkeypatch.delenv("UUMA_KAG_LLM_TIMEOUT_SECONDS", raising=False)

    class SDK:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class AsyncSDK:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class BaseLLMClient:
        def __init__(self):
            self.calls = 0
            self.decorator_calls = 0

        @retry_sync
        def call_with_json_parse(self):
            self.calls += 1
            raise RuntimeError("model failure")

        @retry_async
        async def acall_with_json_parse(self):
            self.calls += 1
            raise RuntimeError("model failure")

    class OpenAIClient(BaseLLMClient):
        def __init__(self, base_url="fixture", model="fixture", api_key="dummy",
                     stream=False, temperature=0.7, timeout=None, **kwargs):
            super().__init__()
            self.base_url = base_url
            self.model = model
            self.api_key = api_key
            self.stream = stream
            self.temperature = temperature
            self.timeout = timeout
            self.kwargs = kwargs
            self.check()

        def check(self):
            self.checked_timeout = self.timeout

        @retry_sync
        def __call__(self):
            self.calls += 1
            raise RuntimeError("model failure")

        @retry_async
        async def acall(self):
            self.calls += 1
            raise RuntimeError("model failure")

    class OtherLLMClient(BaseLLMClient):
        pass

    module = SimpleNamespace(OpenAI=SDK, AsyncOpenAI=AsyncSDK, OpenAIClient=OpenAIClient)
    imports = []

    def load(name):
        imports.append(name)
        assert name == "kag.common.llm.openai_client"
        return module

    monkeypatch.setattr(kag_llm_runtime, "importlib", SimpleNamespace(import_module=load))
    return module, imports, BaseLLMClient, OtherLLMClient


def test_default_does_not_import_or_patch_kag(fake_kag, monkeypatch):
    module, imports, _base, _other = fake_kag
    original = module.OpenAI
    monkeypatch.setenv("UUMA_KAG_LLM_TIMEOUT_SECONDS", "invalid but inactive")
    assert kag_llm_runtime.configure_kag_llm_runtime() is None
    assert imports == []
    assert module.OpenAI is original
    assert hasattr(module.OpenAIClient.__call__, "retry")


@pytest.mark.parametrize("value", ["", "1", "-1", "0.0", " 0", "false"])
def test_invalid_retry_policy_fails_before_import(fake_kag, monkeypatch, value):
    _module, imports, _base, _other = fake_kag
    monkeypatch.setenv("UUMA_KAG_LLM_MAX_RETRIES", value)
    with pytest.raises(ValueError, match="MAX_RETRIES"):
        kag_llm_runtime.configure_kag_llm_runtime()
    assert imports == []


@pytest.mark.parametrize("value", ["", "bad", "nan", "inf", "-inf", "0", "-1", "300.01"])
def test_invalid_timeout_fails_before_import(fake_kag, monkeypatch, value):
    _module, imports, _base, _other = fake_kag
    monkeypatch.setenv("UUMA_KAG_LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("UUMA_KAG_LLM_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="TIMEOUT_SECONDS"):
        kag_llm_runtime.configure_kag_llm_runtime()
    assert imports == []


def test_sdk_sync_and_async_arguments_are_bounded(fake_kag, monkeypatch):
    module, _imports, _base, _other = fake_kag
    sync_sdk, async_sdk = module.OpenAI, module.AsyncOpenAI
    monkeypatch.setenv("UUMA_KAG_LLM_MAX_RETRIES", "0")
    assert kag_llm_runtime.configure_kag_llm_runtime() == {
        "max_retries": 0, "timeout_seconds": 60.0
    }
    assert issubclass(module.OpenAI, sync_sdk)
    assert issubclass(module.AsyncOpenAI, async_sdk)
    for sdk in (module.OpenAI, module.AsyncOpenAI):
        assert sdk(api_key="fixture", max_retries=99, timeout=600).kwargs == {
            "api_key": "fixture", "max_retries": 0, "timeout": 60.0
        }
        assert sdk(timeout=5).kwargs["timeout"] == 5.0
        for timeout in (None, float("inf"), object(), -1):
            assert sdk(timeout=timeout).kwargs["timeout"] == 60.0
        assert sdk().kwargs == {"max_retries": 0, "timeout": 60.0}


def test_repeated_configuration_does_not_stack_sdk_subclasses(fake_kag, monkeypatch):
    module, _imports, _base, _other = fake_kag
    original_sync, original_async = module.OpenAI, module.AsyncOpenAI
    original_client = module.OpenAIClient
    original_init = original_client.__init__
    monkeypatch.setenv("UUMA_KAG_LLM_MAX_RETRIES", "0")
    kag_llm_runtime.configure_kag_llm_runtime()
    sync_class, async_class = module.OpenAI, module.AsyncOpenAI
    bounded_init = module.OpenAIClient.__init__
    method = module.OpenAIClient.call_with_json_parse
    monkeypatch.setenv("UUMA_KAG_LLM_TIMEOUT_SECONDS", "300")
    assert kag_llm_runtime.configure_kag_llm_runtime()["timeout_seconds"] == 300.0
    assert module.OpenAI is sync_class
    assert module.AsyncOpenAI is async_class
    assert module.OpenAIClient is original_client
    assert module.OpenAIClient.__init__ is bounded_init
    assert module._uuma_original_client_init is original_init
    assert module._uuma_original_openai is original_sync
    assert module._uuma_original_async_openai is original_async
    assert module.OpenAIClient.call_with_json_parse is method
    assert module.OpenAI().kwargs["timeout"] == 300.0
    assert module.AsyncOpenAI().kwargs["timeout"] == 300.0
    assert module.OpenAIClient().checked_timeout == 300.0


@pytest.mark.parametrize("timeout, expected", [
    (None, 60.0), (600, 60.0), (5, 5.0), (float("inf"), 60.0), (-1, 60.0)
])
def test_kag_request_timeout_is_bounded_before_constructor_check(
    fake_kag, monkeypatch, timeout, expected
):
    module, _imports, _base, _other = fake_kag
    monkeypatch.setenv("UUMA_KAG_LLM_MAX_RETRIES", "0")
    kag_llm_runtime.configure_kag_llm_runtime()
    client = module.OpenAIClient(timeout=timeout)
    assert client.timeout == expected
    assert client.checked_timeout == expected


def test_kag_default_and_positional_timeout_are_bounded_without_changing_arguments(
    fake_kag, monkeypatch
):
    module, _imports, _base, _other = fake_kag
    monkeypatch.setenv("UUMA_KAG_LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("UUMA_KAG_LLM_TIMEOUT_SECONDS", "45")
    kag_llm_runtime.configure_kag_llm_runtime()
    assert module.OpenAIClient().checked_timeout == 45.0
    for timeout, expected in ((None, 45.0), (900, 45.0), (3, 3.0)):
        client = module.OpenAIClient("local", "model", "fixture-key", True, 0.2, timeout,
                                    max_tokens=17)
        assert client.timeout == expected
        assert client.checked_timeout == expected
        assert (client.base_url, client.model, client.api_key, client.stream, client.temperature) == (
            "local", "model", "fixture-key", True, 0.2
        )
        assert client.kwargs == {"max_tokens": 17}


@pytest.mark.parametrize("name", ["__call__", "call_with_json_parse"])
def test_sync_failure_calls_model_once_without_modifying_other_clients(fake_kag, monkeypatch, name):
    module, _imports, base, other = fake_kag
    base_method = base.call_with_json_parse
    monkeypatch.setenv("UUMA_KAG_LLM_MAX_RETRIES", "0")
    kag_llm_runtime.configure_kag_llm_runtime()
    client = module.OpenAIClient()
    with pytest.raises(RuntimeError, match="model failure"):
        getattr(client, name)()
    assert client.calls == 1
    assert base.call_with_json_parse is base_method
    other_client = other()
    with pytest.raises(RuntimeError, match="model failure"):
        other_client.call_with_json_parse()
    assert other_client.calls == 3


@pytest.mark.parametrize("name", ["acall", "acall_with_json_parse"])
def test_async_failure_calls_model_once_without_modifying_other_clients(fake_kag, monkeypatch, name):
    module, _imports, base, other = fake_kag
    base_method = base.acall_with_json_parse
    monkeypatch.setenv("UUMA_KAG_LLM_MAX_RETRIES", "0")
    kag_llm_runtime.configure_kag_llm_runtime()
    client = module.OpenAIClient()
    with pytest.raises(RuntimeError, match="model failure"):
        asyncio.run(getattr(client, name)())
    assert client.calls == 1
    assert base.acall_with_json_parse is base_method
    other_client = other()
    with pytest.raises(RuntimeError, match="model failure"):
        asyncio.run(other_client.acall_with_json_parse())
    assert other_client.calls == 3


def test_non_tenacity_decorators_are_preserved(fake_kag, monkeypatch):
    module, _imports, _base, _other = fake_kag

    def decorated(self):
        self.decorator_calls += 1
        return "preserved"

    decorated.__wrapped__ = lambda self: "must not unwrap this"
    module.OpenAIClient.__call__ = retry_sync(decorated)
    # A non-Tenacity outer wrapper must remain untouched even if it wraps retry.
    def outer(self):
        return "outer preserved"

    outer.__wrapped__ = module.OpenAIClient.acall
    module.OpenAIClient.acall = outer
    monkeypatch.setenv("UUMA_KAG_LLM_MAX_RETRIES", "0")
    kag_llm_runtime.configure_kag_llm_runtime()
    client = module.OpenAIClient()
    assert client() == "preserved"
    assert client.decorator_calls == 1
    assert module.OpenAIClient.__call__ is decorated
    assert module.OpenAIClient.acall is outer
