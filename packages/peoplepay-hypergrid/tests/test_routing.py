import pytest

from hypergrid.corpus import T0, build_world
from hypergrid.procurement import compute_decision
from hypergrid.routing import (DEFAULT_PROFILES, Config, Facts, GatewayBackend, Router, SimulatedBackend, build_prompt,
                               facts_of, render_explanation, tokens, validate_explanation)

F = Facts("S2", "S1", 1_234_567.0, 4.2, ())


def decisions(n=300, **kw):
    store, reqs, _ = build_world(n, n_synthetic=40, **kw)
    snap = store.snapshot(T0 + 1)
    return reqs, [compute_decision(r, snap, 200) for r in reqs]


def test_validator_accepts_truth_and_rejects_wrong_winner_wrong_amount_and_missing_warning():
    ok = render_explanation(F)
    assert validate_explanation(ok, F)
    assert not validate_explanation(render_explanation(Facts("S1", "S2", F.cost, 4.2, ())), F)
    assert not validate_explanation(render_explanation(Facts("S2", "S1", F.cost * 1.08, 4.2, ())), F)
    flagged = Facts("S2", "S1", F.cost, 4.2, ("SYN.CAT001:stale",))
    assert validate_explanation(render_explanation(flagged), flagged) and not validate_explanation(ok, flagged)


def test_compact_prompt_is_much_smaller_than_the_verbose_prompt():
    reqs, res = decisions(20)
    f = facts_of(reqs[0], res[0])
    assert tokens(build_prompt(reqs[0], res[0], f, "compact")) < tokens(build_prompt(reqs[0], res[0], f, "verbose")) * 0.6


H = Config("H", "adaptive", "compact", det_first=True, cache=True, validate_escalate=True)


class Spy(SimulatedBackend):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.seen = []
    def call(self, profile, key, prompt, facts, hard, local_only=False):
        self.seen.append((profile.name, profile.local, local_only))
        return super().call(profile, key, prompt, facts, hard, local_only)


def test_local_only_data_never_reaches_a_cloud_model_in_adaptive_and_static_modes():
    reqs, res = decisions(500, local_only_rate=0.5)
    for cfg in (H, Config("C", "static")):
        spy = Spy(); router = Router(cfg, spy)
        for r, d in zip(reqs, res):
            out = router.explain(r, d)
            assert not out.privacy_violation
        assert all(local for _, local, lo in spy.seen if lo) and any(lo for *_, lo in spy.seen)


def test_local_model_failure_falls_back_to_deterministic_text_never_to_the_cloud():
    reqs, res = decisions(300, local_only_rate=1.0)
    broken = Spy(accuracy_override={("local", True): 0.0, ("local", False): 0.0}, silent_error_share=0.0)
    router = Router(H, broken)
    outs = [router.explain(r, d) for r, d in zip(reqs, res)]
    assert all(not o.privacy_violation for o in outs) and all(o.verified for o in outs)
    assert any(o.path.endswith("template") and "local" in o.path for o in outs)
    assert all(not isinstance(c.model, str) or c.local for o in outs for c in o.calls)


def test_the_single_model_baseline_does_violate_local_only_which_is_why_it_is_a_baseline():
    reqs, res = decisions(300, local_only_rate=0.5)
    router = Router(Config("A", "single_large"))
    assert sum(router.explain(r, d).privacy_violation for r, d in zip(reqs, res)) > 0


def test_easy_decisions_use_templates_and_make_no_model_call():
    reqs, res = decisions(300)
    router = Router(H)
    easy = [(r, d) for r, d in zip(reqs, res) if not d.hard]
    assert easy and all(router.explain(r, d).calls == [] for r, d in easy)


def test_escalation_happens_only_after_a_failed_validation_and_ends_verified():
    reqs, res = decisions(400)
    router = Router(H, SimulatedBackend(accuracy_override={("small", True): 0.0, ("small", False): 0.0}, silent_error_share=0.0))
    outs = [router.explain(r, d) for r, d in zip(reqs, res)]
    esc = [o for o in outs if len(o.calls) > 1]
    assert esc and all(o.calls[0].valid is False and o.verified for o in esc)


def test_cache_hits_on_identical_facts_and_is_segregated_by_data_class():
    reqs, res = decisions(400, repeat_rate=0.6)
    router = Router(H)
    outs = [router.explain(r, d) for r, d in zip(reqs, res)]
    assert sum(o.cache_hit for o in outs) > 0
    a, d = reqs[0], res[0]
    assert Router.cache_key(facts_of(a, d), "INTERNAL", "compact") != Router.cache_key(facts_of(a, d), "LOCAL_ONLY", "compact")


def test_hypergrid_beats_single_model_on_cost_and_the_accuracy_gap_is_visible_not_hidden():
    from hypergrid.bench import run_config
    reqs, res = decisions(600)
    A = run_config(Config("A", "single_large"), reqs, res, 0.8, 1)
    Hr = run_config(H, reqs, res, 0.8, 8)
    assert Hr["total_cost_usd"] < A["total_cost_usd"] and Hr["unverified_outputs"] == 0
    assert "correct" in Hr and "accepted_wrong" in Hr                       # quality is always reported next to cost


def test_gateway_backend_drives_the_real_model_gateway_and_refuses_cloud_for_local_only_work():
    from peoplepay_models.adapters.mock import MockAdapter
    from peoplepay_models.gateway import ModelGateway
    from peoplepay_models.netguard import NetPolicy
    from peoplepay_models.registry import default_registry
    from peoplepay_models.store import ModelStore
    from peoplepay_models.transport import FakeTransport
    MockAdapter.reset()
    gw = ModelGateway(store=ModelStore(), transport=FakeTransport(), registry=default_registry(enable_mock=True), net_policy=NetPolicy(mode="self_hosted"))
    cloud = gw.connect("u", "mock", "cloud", {"models": [{"id": "big", "name": "Big"}, {"id": "tiny", "name": "Tiny"}]})["connection"]["id"]
    local = gw.connect("u", "mock", "local", {"local": True, "models": [{"id": "loc", "name": "Loc"}]})["connection"]["id"]
    backend = GatewayBackend(gw, "u", {"large": f"{cloud}::big", "small": f"{cloud}::tiny", "local": f"{local}::loc"})
    reqs, res = decisions(200, local_only_rate=0.5)
    router = Router(H, backend)
    outs = [router.explain(r, d) for r, d in zip(reqs, res)]
    # mock replies are not valid explanations -> validation fails -> escalation -> deterministic fallback; never unverified
    assert all(o.verified and not o.privacy_violation for o in outs)
    from tests_helpers import calls
    assert calls(local) > 0 and calls(cloud) > 0
    # even a router bug cannot leak: asking the backend for the CLOUD profile with local_only is refused by the Gateway
    _, rec = backend.call(DEFAULT_PROFILES["large"], "k", "p", F, True, local_only=True)
    assert rec.valid is False and rec.out_tok == 0
