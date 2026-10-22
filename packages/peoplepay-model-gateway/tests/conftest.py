import pytest

from peoplepay_models.adapters.mock import MockAdapter
from peoplepay_models.gateway import ModelGateway
from peoplepay_models.netguard import NetPolicy
from peoplepay_models.registry import default_registry
from peoplepay_models.store import ModelStore
from peoplepay_models.transport import FakeTransport
from peoplepay_models.vault import MemoryVault


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t
    def advance(self, s): self.t += s


@pytest.fixture(autouse=True)
def _reset_mock():
    MockAdapter.reset()
    yield
    MockAdapter.reset()


@pytest.fixture
def fake_provider_dns(monkeypatch):
    """Fixture transport tests must not resolve a public provider on the network.

    Keep the real URL policy validation, inject only the DNS answer for the one
    fake OpenAI endpoint. Direct netguard/rebinding tests remain untouched.
    """
    import socket
    import peoplepay_models.gateway as module
    from peoplepay_models.netguard import validate_url

    def resolve(host, port, **kwargs):
        if host == "api.openai.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
        return socket.getaddrinfo(host, port, **kwargs)

    monkeypatch.setattr(module, "validate_url", lambda url, policy: validate_url(url, policy, resolver=resolve))


@pytest.fixture
def gw(fake_provider_dns):
    return ModelGateway(store=ModelStore(), vault=MemoryVault(), transport=FakeTransport(),
                        registry=default_registry(enable_mock=True), net_policy=NetPolicy(mode="self_hosted"))


from mg_helpers import FAST, VISION, DEEP, add_mock  # noqa: F401
