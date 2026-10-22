"""Opt-in retry and timeout bounds for the KAG OpenAI client module only."""

from __future__ import annotations

import importlib
import inspect
import math
import os
import threading
from functools import wraps
from typing import Any

_configuration_lock = threading.Lock()


def _timeout(value: Any, limit: float) -> float:
    """Keep a smaller numeric timeout; replace unbounded SDK timeout objects."""
    try:
        requested = float(value)
    except (TypeError, ValueError, OverflowError):
        return limit
    return min(requested, limit) if math.isfinite(requested) and requested > 0 else limit


def _without_tenacity(method: Any) -> Any:
    # A __wrapped__ link alone may belong to a different decorator. Stop there.
    while hasattr(method, "retry") and hasattr(method, "__wrapped__"):
        method = method.__wrapped__
    return method


def configure_kag_llm_runtime() -> dict[str, int | float] | None:
    """Bound the explicitly enabled KAG client without changing vendor sources.

    This policy lasts for the process lifetime. With no opt-in variable, this
    function does not import KAG or change its existing behavior. Only zero
    retries are supported: a failed external operation must be reconciled before
    another model request can be made by the caller.
    """
    retries = os.environ.get("UUMA_KAG_LLM_MAX_RETRIES")
    if retries is None:
        return None
    if retries != "0":
        raise ValueError("UUMA_KAG_LLM_MAX_RETRIES must be exactly '0'")
    try:
        timeout = float(os.environ.get("UUMA_KAG_LLM_TIMEOUT_SECONDS", "60"))
    except (ValueError, OverflowError) as error:
        raise ValueError("UUMA_KAG_LLM_TIMEOUT_SECONDS must be finite and in (0, 300]") from error
    if not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise ValueError("UUMA_KAG_LLM_TIMEOUT_SECONDS must be finite and in (0, 300]")
    policy = {"max_retries": 0, "timeout_seconds": timeout}
    with _configuration_lock:
        module = importlib.import_module("kag.common.llm.openai_client")
        if not hasattr(module, "_uuma_original_openai"):
            module._uuma_original_openai = module.OpenAI
            module._uuma_original_async_openai = module.AsyncOpenAI

            class BoundedOpenAI(module._uuma_original_openai):
                def __init__(self, *args: Any, **kwargs: Any) -> None:
                    kwargs["max_retries"] = 0
                    kwargs["timeout"] = _timeout(
                        kwargs.get("timeout"), module._uuma_llm_policy["timeout_seconds"]
                    )
                    super().__init__(*args, **kwargs)

            class BoundedAsyncOpenAI(module._uuma_original_async_openai):
                def __init__(self, *args: Any, **kwargs: Any) -> None:
                    kwargs["max_retries"] = 0
                    kwargs["timeout"] = _timeout(
                        kwargs.get("timeout"), module._uuma_llm_policy["timeout_seconds"]
                    )
                    super().__init__(*args, **kwargs)

            module._uuma_bounded_openai = BoundedOpenAI
            module._uuma_bounded_async_openai = BoundedAsyncOpenAI
        module._uuma_llm_policy = dict(policy)
        module.OpenAI = module._uuma_bounded_openai
        module.AsyncOpenAI = module._uuma_bounded_async_openai
        if not hasattr(module, "_uuma_original_client_init"):
            original_init = module.OpenAIClient.__init__
            signature = inspect.signature(original_init)
            if "timeout" not in signature.parameters:
                raise RuntimeError("KAG OpenAIClient constructor must expose timeout")

            @wraps(original_init)
            def bounded_client_init(self: Any, *args: Any, **kwargs: Any) -> None:
                bound = signature.bind(self, *args, **kwargs)
                bound.apply_defaults()
                bound.arguments["timeout"] = _timeout(
                    bound.arguments["timeout"], module._uuma_llm_policy["timeout_seconds"]
                )
                # KAG stores timeout and may run check() inside its constructor.
                # Its request-level timeout must already be bounded at that point.
                original_init(*bound.args, **bound.kwargs)

            module._uuma_original_client_init = original_init
            module._uuma_bounded_client_init = bounded_client_init
        module.OpenAIClient.__init__ = module._uuma_bounded_client_init
        for name in ("__call__", "acall", "call_with_json_parse", "acall_with_json_parse"):
            method = getattr(module.OpenAIClient, name, None)
            if method is not None:
                unwrapped = _without_tenacity(method)
                if unwrapped is not method:
                    # Inherited JSON helpers are overridden on this client only.
                    setattr(module.OpenAIClient, name, unwrapped)
    return policy
