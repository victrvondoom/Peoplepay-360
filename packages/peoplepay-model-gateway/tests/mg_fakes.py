"""Realistic wire-format fixtures for each adapter, used by the shared contract suite."""
import json


def oa_models(ids):
    return {"object": "list", "data": [{"id": i, "object": "model", "owned_by": "x"} for i in ids]}


def oa_chat(text="hello", tool=None, usage=True, model="m1"):
    msg = {"role": "assistant", "content": text}
    if tool:
        msg = {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": tool}]}
    out = {"model": model, "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}]}
    if usage:
        out["usage"] = {"prompt_tokens": 7, "completion_tokens": 3, "prompt_tokens_details": {"cached_tokens": 2}}
    return out


def oa_sse(chunks, usage=True):
    lines = []
    for c in chunks:
        lines.append("data: " + json.dumps({"model": "m1", "choices": [{"delta": {"content": c}}]}) + "\n\n")
    lines.append("data: " + json.dumps({"model": "m1", "choices": [{"delta": {}, "finish_reason": "stop"}],
                                        **({"usage": {"prompt_tokens": 7, "completion_tokens": 3}} if usage else {})}) + "\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines)


def openai_like(models=("m1",), *, status=200, fail_status=None, tool=None, headers=None):
    def h(method, url, hdrs, body):
        if fail_status:
            return fail_status, {"error": {"message": "nope sk-SECRETSECRET1234"}}, headers or {}
        if url.endswith("/models"):
            return 200, oa_models(models)
        if url.endswith("/chat/completions"):
            if body.get("stream"):
                return 200, oa_sse(["Hel", "lo"])
            return 200, oa_chat(tool=tool)
        return 404, {"error": "?"}
    return h


def anthropic_like(*, fail_status=None, bad_tool=False):
    def h(method, url, hdrs, body):
        if fail_status:
            return fail_status, {"type": "error", "error": {"type": "authentication_error", "message": "bad key"}}
        if "/v1/models" in url:
            return 200, {"data": [{"id": "claude-x", "display_name": "Claude X"}], "has_more": False}
        if url.endswith("/v1/messages"):
            if body.get("stream"):
                ev = [{"type": "message_start", "message": {"model": "claude-x", "usage": {"input_tokens": 5}}},
                      {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
                      {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hel"}},
                      {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "lo"}},
                      {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}},
                      {"type": "message_stop"}]
                return 200, "".join("data: " + json.dumps(e) + "\n\n" for e in ev)
            content = [{"type": "tool_use", "id": "t1", "name": "x", "input": "notadict"}] if bad_tool else [{"type": "text", "text": "hello"}]
            return 200, {"model": "claude-x", "content": content, "stop_reason": "end_turn", "usage": {"input_tokens": 7, "output_tokens": 3}}
        return 404, {}
    return h


def ollama_like(*, fail=None):
    def h(method, url, hdrs, body):
        if fail:
            return fail
        if url.endswith("/api/tags"):
            return 200, {"models": [{"name": "qwen:7b", "details": {"family": "qwen"}}]}
        if url.endswith("/api/show"):
            return 200, {"capabilities": ["completion", "tools"], "model_info": {"qwen2.context_length": 32768}}
        if url.endswith("/api/chat"):
            if body.get("stream"):
                return 200, json.dumps({"message": {"content": "Hel"}}) + "\n" + json.dumps({"message": {"content": "lo"}}) + "\n" + \
                    json.dumps({"done": True, "done_reason": "stop", "prompt_eval_count": 7, "eval_count": 3, "model": "qwen:7b"}) + "\n"
            return 200, {"model": "qwen:7b", "message": {"role": "assistant", "content": "hello"}, "done": True, "done_reason": "stop",
                         "prompt_eval_count": 7, "eval_count": 3}
        return 404, {}
    return h


class FakeBedrockRuntime:
    def __init__(self, error=None): self.error = error
    def converse(self, **kw):
        if self.error: raise self.error
        return {"output": {"message": {"content": [{"text": "hello"}]}}, "usage": {"inputTokens": 7, "outputTokens": 3}, "stopReason": "end_turn"}
    def converse_stream(self, **kw):
        if self.error: raise self.error
        return {"stream": [{"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "Hel"}}},
                           {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "lo"}}},
                           {"messageStop": {"stopReason": "end_turn"}},
                           {"metadata": {"usage": {"inputTokens": 7, "outputTokens": 3}}}]}


class FakeBedrock:
    def __init__(self, error=None): self.error = error
    def list_foundation_models(self, **kw):
        if self.error: raise self.error
        return {"modelSummaries": [
            {"modelId": "anthropic.claude-x-v1:0", "modelName": "Claude X", "providerName": "Anthropic", "inputModalities": ["TEXT", "IMAGE"],
             "responseStreamingSupported": True, "inferenceTypesSupported": ["ON_DEMAND"]},
            {"modelId": "amazon.profile-only-v1:0", "modelName": "Needs profile", "inputModalities": ["TEXT"], "inferenceTypesSupported": ["INFERENCE_PROFILE"]}]}
    def list_inference_profiles(self):
        return {"inferenceProfileSummaries": []}


class ClientError(Exception):
    def __init__(self, code, msg="m"):
        self.response = {"Error": {"Code": code, "Message": msg}}
        super().__init__(code)


def bedrock_factory(error=None):
    def f(service, config, secrets):
        return FakeBedrockRuntime(error) if service == "bedrock-runtime" else FakeBedrock(error)
    return f


def decision_like(*, confidence=0.9, bad=False):
    def h(method, url, hdrs, body):
        if url.endswith("/health"):
            return 200, {"ok": True}
        if url.endswith("/models"):
            return 200, {"models": [{"id": "d1", "question_types": ["BOOLEAN", "CHOICE", "SCORE"]}]}
        if url.endswith("/decide"):
            ans = []
            for q in body["questions"]:
                v = {"BOOLEAN": True, "CHOICE": (q.get("choices") or ["x"])[0], "SCORE": 0.5, "RATING": 3}[q["type"]]
                if bad: v = "garbage"
                ans.append({"id": q["id"], "value": v, **({"confidence": confidence} if confidence is not None else {})})
            return 200, {"answers": ans}
        return 404, {}
    return h
