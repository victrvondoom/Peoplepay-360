"""LIVE tests: discover + tiny inference on whatever credentials exist. Skipped otherwise. Never run in default CI."""
import os
import socket

import pytest

from peoplepay_models.canonical import InferenceRequest, Message, ModelSelection
from peoplepay_models.gateway import ModelGateway
from peoplepay_models.netguard import NetPolicy
from peoplepay_models.registry import default_registry
from peoplepay_models.store import ModelStore

pytestmark = pytest.mark.skipif(os.environ.get("PEOPLEPAY_LIVE_TESTS") != "1", reason="set PEOPLEPAY_LIVE_TESTS=1 to run live provider tests")

CASES = [("openai", "OPENAI_API_KEY", {}), ("anthropic", "ANTHROPIC_API_KEY", {}), ("openrouter", "OPENROUTER_API_KEY", {}),
         ("nvidia_nim", "NVIDIA_API_KEY", {})]


def _ollama_up():
    try:
        socket.create_connection(("127.0.0.1", 11434), 1).close(); return True
    except OSError:
        return False


@pytest.mark.parametrize("provider,env,extra", CASES)
def test_live_discover_and_invoke(provider, env, extra):
    if not os.environ.get(env):
        pytest.skip(f"{env} not set")
    gw = ModelGateway(store=ModelStore(), registry=default_registry(), net_policy=NetPolicy(mode="self_hosted"))
    out = gw.connect("live", provider, provider, {"api_key": os.environ[env], **extra})
    assert out["test"]["ok"], out["test"]
    models = [m for m in gw.list_models("live")["models"] if m["selectable_as_chat"]]
    assert models, "discovery returned no chat models"
    r = gw.infer("live", InferenceRequest(messages=[Message.user("Reply with the single word: ok")], max_output_tokens=16,
                                           selection=ModelSelection("model", models[0]["provider_model_id"], one_shot=True)))
    assert r.text


def test_live_ollama():
    if not _ollama_up():
        pytest.skip("Ollama not reachable on 127.0.0.1:11434")
    gw = ModelGateway(store=ModelStore(), registry=default_registry(), net_policy=NetPolicy(mode="self_hosted"))
    assert gw.connect("live", "ollama", "local", {"base_url": "http://127.0.0.1:11434"})["test"]["ok"]
    gw.set_prefs("live", {"local_only": True})
    assert gw.infer("live", InferenceRequest(messages=[Message.user("Say ok")], max_output_tokens=16)).served_by.route.startswith("Local")
