"""Map existing environment variables onto system ProviderConnections.

Existing deployments keep working unchanged: the same variables they already set become
system connections (secrets held in process memory only, never persisted, never
returned). Nothing is registered unless its variable is present.
"""
from __future__ import annotations

import os
from typing import Mapping

from .gateway import ModelGateway


def register_env_connections(gw: ModelGateway, env: Mapping[str, str] | None = None) -> list[str]:
    env = os.environ if env is None else env
    made: list[str] = []

    def reg(cid, ptype, name, config, secrets):
        if gw.providers.is_enabled(ptype):
            gw.register_system_connection(cid, ptype, name, config, secrets)
            made.append(cid)

    if env.get("OPENAI_API_KEY"):
        cfg = {"base_url": env["OPENAI_BASE_URL"]} if env.get("OPENAI_BASE_URL") else {}
        reg("sys_openai", "openai", "OpenAI (environment)", cfg, {"api_key": env["OPENAI_API_KEY"]})
    if env.get("ANTHROPIC_API_KEY"):
        reg("sys_anthropic", "anthropic", "Anthropic (environment)", {}, {"api_key": env["ANTHROPIC_API_KEY"]})
    if env.get("OPENROUTER_API_KEY"):
        reg("sys_openrouter", "openrouter", "OpenRouter (environment)", {}, {"api_key": env["OPENROUTER_API_KEY"]})
    nvidia = env.get("NVIDIA_API_KEY") or env.get("NVIDIA_NIM_API_KEY") or env.get("NIM_API_KEY")
    if nvidia or env.get("NIM_BASE_URL"):
        cfg = {"base_url": env["NIM_BASE_URL"]} if env.get("NIM_BASE_URL") else {}
        reg("sys_nvidia_nim", "nvidia_nim", "NVIDIA NIM (environment)", cfg, {"api_key": nvidia} if nvidia else {})
    region = env.get("BEDROCK_REGION") or env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION")
    if env.get("PEOPLEPAY_ENABLE_BEDROCK") or (region and (env.get("AWS_ACCESS_KEY_ID") or env.get("AWS_PROFILE") or env.get("AWS_ROLE_ARN"))):
        reg("sys_bedrock", "bedrock", "Amazon Bedrock (environment)", {"region": region or "us-east-1", "credential_strategy": "default_chain"}, {})
    host = env.get("OLLAMA_HOST") or env.get("OLLAMA_BASE_URL")
    if host:
        if not host.startswith("http"):
            host = "http://" + host
        reg("sys_ollama", "ollama", "Ollama (environment)", {"base_url": host}, {})
    elif gw.net.mode == "self_hosted" and env.get("PEOPLEPAY_MODELS_PROBE_LOCAL_OLLAMA", "1") != "0":
        reg("sys_ollama", "ollama", "Ollama (default local address)", {"base_url": "http://127.0.0.1:11434"}, {})
    for pid, ptype in (("JEV", "jev"), ("LAYA", "laya")):
        if env.get(f"{pid}_BASE_URL"):
            sec = {"api_key": env[f"{pid}_API_KEY"]} if env.get(f"{pid}_API_KEY") else {}
            reg(f"sys_{ptype}", ptype, f"{pid.title() if pid != 'JEV' else 'JEV'} (environment)", {"base_url": env[f"{pid}_BASE_URL"]}, sec)
    if env.get("PEOPLEPAY_MODELS_ENABLE_MOCK") == "1" and gw.providers.is_enabled("mock"):
        reg("sys_mock_cloud", "mock", "Mock cloud (demo)", {"models": [
            {"id": "mock-fast", "name": "Mock Fast", "context": 32000},
            {"id": "mock-vision", "name": "Mock Vision", "vision": True, "tools": True, "context": 64000},
            {"id": "mock-deep", "name": "Mock Deep", "reasoning": True, "tools": True, "vision": True, "context": 200000}]}, {})
        reg("sys_mock_local", "mock", "Mock local (demo)", {"local": True, "route_label": "Local (mock)", "privacy": "local", "models": [
            {"id": "mock-local-qwen", "name": "Mock Local Qwen", "context": 16000}]}, {})
    return made
