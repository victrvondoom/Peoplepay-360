"""Every adapter passes the same suite: discover, health, simple inference, stream,
invalid credentials, normalization, malformed output. CONTRACT/MOCK verified only --
no live provider is called."""
import pytest

from peoplepay_models.adapters.anthropic import AnthropicAdapter
from peoplepay_models.adapters.base import CallSpec
from peoplepay_models.adapters.bedrock import BedrockAdapter
from peoplepay_models.adapters.ollama import OllamaAdapter
from peoplepay_models.adapters.openai_compat import CustomOpenAIAdapter, NvidiaNimAdapter, OpenAIAdapter, OpenRouterAdapter
from peoplepay_models.canonical import Health, Message, TextPart, ToolCallPart, ToolDefinition
from peoplepay_models.errors import ErrorCode, GatewayError
from peoplepay_models.transport import FakeTransport

import mg_fakes as fakes

SECRET = "sk-SECRETSECRET1234"


def mk(kind, *, fail_status=None, tool=None, bad_tool=False):
    S = {"api_key": SECRET}
    if kind == "openai":
        return OpenAIAdapter("c", {}, S, FakeTransport(fakes.openai_like(fail_status=fail_status, tool=tool)))
    if kind == "nim":
        return NvidiaNimAdapter("c", {}, S, FakeTransport(fakes.openai_like(fail_status=fail_status, tool=tool)))
    if kind == "openrouter":
        return OpenRouterAdapter("c", {}, S, FakeTransport(fakes.openai_like(fail_status=fail_status, tool=tool)))
    if kind == "custom":
        return CustomOpenAIAdapter("c", {"base_url": "http://x/v1"}, S, FakeTransport(fakes.openai_like(fail_status=fail_status, tool=tool)))
    if kind == "anthropic":
        return AnthropicAdapter("c", {}, S, FakeTransport(fakes.anthropic_like(fail_status=fail_status, bad_tool=bad_tool)))
    if kind == "ollama":
        fail = (fail_status, {"error": "x"}) if fail_status else None
        return OllamaAdapter("c", {}, {}, FakeTransport(fakes.ollama_like(fail=fail)))
    if kind == "bedrock":
        err = fakes.ClientError({401: "UnrecognizedClientException"}.get(fail_status, "ThrottlingException"), "denied") if fail_status else None
        return BedrockAdapter("c", {"region": "us-east-1"}, {}, FakeTransport(), client_factory=fakes.bedrock_factory(err))
    raise KeyError(kind)


KINDS = ["openai", "nim", "openrouter", "custom", "anthropic", "ollama", "bedrock"]


def spec(model="m1", **kw):
    return CallSpec(provider_model_id=model, messages=[Message.user("hi")], **kw)


@pytest.mark.parametrize("kind", KINDS)
def test_discover_and_health(kind):
    a = mk(kind)
    routes = a.discover_models()
    assert routes and all(r.provider_id == a.manifest.id and r.provider_model_id for r in routes)
    assert all(r.last_discovered_at for r in routes)
    assert a.health().state == Health.HEALTHY


@pytest.mark.parametrize("kind", KINDS)
def test_simple_inference_normalized(kind):
    a = mk(kind)
    res = a.generate(spec())
    assert "".join(p.text for p in res.parts) == "hello"
    assert res.usage.input_tokens == 7 and res.usage.output_tokens == 3
    assert res.usage.estimated_cost is None          # never invented


@pytest.mark.parametrize("kind", KINDS)
def test_stream_normalized(kind):
    a = mk(kind)
    evs = list(a.stream(spec()))
    types = [e.type for e in evs]
    assert types[0] == "response.started" and types[-1] == "response.completed" and "usage" in types
    assert "".join(e.data["text"] for e in evs if e.type == "text.delta").replace(" ", "") == "Hello"


@pytest.mark.parametrize("kind", KINDS)
def test_invalid_credentials(kind):
    a = mk(kind, fail_status=401)
    with pytest.raises(GatewayError) as ei:
        a.generate(spec())
    assert ei.value.code == ErrorCode.INVALID_CREDENTIALS
    assert SECRET not in str(ei.value) and SECRET not in ei.value.detail
    assert a.validate_credentials().state == Health.AUTH_ERROR


@pytest.mark.parametrize("kind", ["openai", "nim", "openrouter", "custom", "anthropic", "ollama"])
def test_rate_limit_and_retry_after(kind):
    a = mk(kind)
    a.transport.handler = lambda *x: (429, {"error": {"message": "slow down"}}, {"retry-after": "7"})
    with pytest.raises(GatewayError) as ei:
        a.generate(spec())
    assert ei.value.code == ErrorCode.RATE_LIMITED and ei.value.retry_after == 7.0 and ei.value.fallback_eligible


def test_bedrock_error_mapping():
    a = mk("bedrock", fail_status=429)
    with pytest.raises(GatewayError) as ei:
        a.generate(spec())
    assert ei.value.code == ErrorCode.RATE_LIMITED
    for code, want in [("AccessDeniedException", ErrorCode.MODEL_UNAVAILABLE), ("ModelTimeoutException", ErrorCode.TIMEOUT),
                       ("ResourceNotFoundException", ErrorCode.MODEL_NOT_FOUND)]:
        a = BedrockAdapter("c", {}, {}, FakeTransport(), client_factory=fakes.bedrock_factory(fakes.ClientError(code, "x")))
        with pytest.raises(GatewayError) as ei:
            a.generate(spec())
        assert ei.value.code == want


@pytest.mark.parametrize("kind", ["openai", "nim", "openrouter", "custom"])
def test_malformed_tool_call_rejected(kind):
    a = mk(kind, tool={"name": "buy", "arguments": "{not json"})
    with pytest.raises(GatewayError) as ei:
        a.generate(spec(tools=[ToolDefinition("buy", "d")]))
    assert ei.value.code == ErrorCode.INVALID_RESPONSE


def test_valid_tool_call_normalized():
    a = mk("openai", tool={"name": "buy", "arguments": '{"sku": "A1"}'})
    res = a.generate(spec(tools=[ToolDefinition("buy", "d")]))
    call = res.parts[0]
    assert isinstance(call, ToolCallPart) and call.name == "buy" and call.arguments == {"sku": "A1"}


def test_anthropic_malformed_tool_rejected():
    with pytest.raises(GatewayError) as ei:
        mk("anthropic", bad_tool=True).generate(spec())
    assert ei.value.code == ErrorCode.INVALID_RESPONSE


def test_timeout_is_normalized():
    a = mk("openai")
    a.transport.handler = lambda *x: GatewayError(ErrorCode.TIMEOUT, "t")
    with pytest.raises(GatewayError) as ei:
        a.generate(spec())
    assert ei.value.code == ErrorCode.TIMEOUT and ei.value.fallback_eligible


def test_ollama_offline_is_local_error():
    a = mk("ollama")
    a.transport.handler = lambda *x: GatewayError(ErrorCode.PROVIDER_UNAVAILABLE, "refused")
    with pytest.raises(GatewayError) as ei:
        a.generate(spec())
    assert ei.value.code == ErrorCode.LOCAL_PROVIDER_OFFLINE
    assert a.health().state == Health.UNAVAILABLE


def test_ollama_capabilities_from_provider_metadata():
    r = mk("ollama").discover_models()[0]
    assert r.capabilities.has(__import__("peoplepay_models").Capability.TOOLS)
    assert r.capabilities.items["tools"] == "provider_metadata"
    assert r.context_window == 32768 and r.local and r.privacy.value == "local"


def test_openrouter_metadata_and_pricing_and_unknown_fields_stay_null():
    def h(m, url, hd, b):
        return 200, {"data": [{"id": "vendor/model-a", "name": "A", "context_length": 128000,
                               "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
                               "supported_parameters": ["tools", "structured_outputs"],
                               "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
                              {"id": "vendor/model-b", "name": "B"}]}
    a = OpenRouterAdapter("c", {}, {"api_key": "k"}, FakeTransport(h))
    ra, rb = a.discover_models()
    assert ra.capabilities.has(__import__("peoplepay_models").Capability.VISION) and ra.context_window == 128000
    assert ra.pricing == {"input_per_mtok": pytest.approx(1.0), "output_per_mtok": pytest.approx(2.0)}
    assert rb.pricing is None and rb.context_window is None and rb.max_output is None


def test_openrouter_records_actual_upstream():
    def h(m, url, hd, b):
        d = fakes.oa_chat(); d["provider"] = "UpstreamCo"; return 200, d
    a = OpenRouterAdapter("c", {}, {"api_key": "k"}, FakeTransport(h))
    assert a.generate(spec()).served_via == "UpstreamCo"


def test_nim_selfhosted_uses_readiness_probe():
    seen = []
    def h(m, url, hd, b):
        seen.append(url); return 200, {}
    a = NvidiaNimAdapter("c", {"base_url": "http://nim.internal:8000/v1"}, {}, FakeTransport(h))
    assert a.health().state == Health.HEALTHY and seen[0].endswith("/v1/health/ready")


def test_custom_headers_are_sanitized():
    a = CustomOpenAIAdapter("c", {"base_url": "http://x/v1", "headers": {"X-Ok": "1", "Host": "evil", "Authorization": "x",
                                                                       "Bad\r\nHeader": "v", "X-Inj": "a\r\nb"}}, {"api_key": "k"},
                            FakeTransport(fakes.openai_like()))
    a.generate(spec())
    h = a.transport.calls[0]["headers"]
    assert h["X-Ok"] == "1" and "Host" not in h and h["Authorization"] == "Bearer k" and "X-Inj" not in h


def test_custom_manual_models_when_no_discovery():
    a = CustomOpenAIAdapter("c", {"base_url": "http://x/v1", "manual_models": "a, b"}, {},
                            FakeTransport(lambda *x: (404, {"error": "no"})))
    assert [r.provider_model_id for r in a.discover_models()] == ["a", "b"]


def test_custom_capability_override_labelled_as_user_override():
    a = CustomOpenAIAdapter("c", {"base_url": "http://x/v1", "capability_overrides": {"vision": True}}, {},
                            FakeTransport(fakes.openai_like(models=("zzz",))))
    r = a.discover_models()[0]
    assert r.capabilities.items["vision"] == "user_override"


def test_bedrock_discovery_skips_profile_only_and_reads_modalities():
    a = mk("bedrock")
    routes = a.discover_models()
    ids = [r.provider_model_id for r in routes]
    assert ids == ["anthropic.claude-x-v1:0"]                  # profile-only model not invocable => not offered
    assert routes[0].capabilities.items["vision"] == "provider_metadata" and routes[0].region == "us-east-1"


def test_image_to_non_inline_provider_is_not_silently_dropped():
    from peoplepay_models.canonical import FilePart
    with pytest.raises(GatewayError) as ei:
        mk("openai").generate(CallSpec("m1", [Message("user", [TextPart("x"), FilePart("a.pdf", "application/pdf", "AAAA")])]))
    assert ei.value.code == ErrorCode.UNSUPPORTED_CAPABILITY


def test_reasoning_preference_unsupported_is_metadata_not_error():
    from peoplepay_models.canonical import Reasoning
    res = mk("custom").generate(spec(reasoning=Reasoning.DEEP))
    assert any("not mapped" in n for n in res.notes)
