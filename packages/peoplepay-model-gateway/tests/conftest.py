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
def gw():
    return ModelGateway(store=ModelStore(), vault=MemoryVault(), transport=FakeTransport(),
                        registry=default_registry(enable_mock=True), net_policy=NetPolicy(mode="self_hosted"))


from mg_helpers import FAST, VISION, DEEP, add_mock  # noqa: F401
