"""Built-in tools registered on import. Each is a genuine working
implementation, not a stub -- except currency_conversion, which uses a small
static reference table and says so explicitly rather than pretending to be a
live FX feed (no live rates API is configured in this deployment)."""
from __future__ import annotations

import ast
import operator
from datetime import date, datetime, timedelta

from app.agents.tools.registry import tool_registry
from app.models.domain import Domain
from app.rag.retrieval.qdrant_service import qdrant_service
from app.services.reindex_service import _read_file  # reuse the same PDF/text extraction the reindex pipeline uses

# ---- Calculator: AST-restricted arithmetic (no eval()) ----------------

_ALLOWED_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_ALLOWED_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


async def calculator(expression: str) -> dict:
    """Evaluate a plain arithmetic expression (+ - * / ** % and parentheses only)."""
    try:
        tree = ast.parse(expression, mode="eval")
        value = _eval_node(tree.body)
    except (SyntaxError, ValueError, ZeroDivisionError, TypeError) as exc:
        raise ValueError(f"Invalid expression '{expression}': {exc}") from exc
    return {"expression": expression, "value": value}


# ---- Date calculations --------------------------------------------------

async def date_diff(start_date: str, end_date: str) -> dict:
    """Days between two ISO dates (YYYY-MM-DD)."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    return {"start_date": start_date, "end_date": end_date, "days": (end - start).days}


async def date_add(start_date: str, days: int) -> dict:
    """A date `days` after (or before, if negative) start_date."""
    start = date.fromisoformat(start_date)
    result = start + timedelta(days=days)
    return {"start_date": start_date, "days_added": days, "result_date": result.isoformat()}


async def today() -> dict:
    return {"today": datetime.now().date().isoformat()}


# ---- PDF / document parser -----------------------------------------------

async def pdf_parser(file_path: str, max_chars: int = 5000) -> dict:
    """Extract text from a PDF or text file already on disk, reusing the
    same extraction path the reindex pipeline uses."""
    from pathlib import Path
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {file_path}")
    text = _read_file(path)
    return {"file_path": file_path, "chars_extracted": len(text), "text": text[:max_chars]}


# ---- Currency conversion (static table -- see docstring) -----------------

# NOTE: this is a small static reference table, not a live feed. No FX-rate
# API key/service is configured in this deployment; wire a real provider
# (e.g. exchangerate-api, RBI reference rate) before relying on this for
# anything beyond rough, non-time-sensitive estimates.
_STATIC_INR_RATES = {"USD": 83.0, "EUR": 90.0, "GBP": 105.0, "AED": 22.6, "INR": 1.0}


async def currency_conversion(amount: float, from_currency: str, to_currency: str) -> dict:
    from_currency, to_currency = from_currency.upper(), to_currency.upper()
    if from_currency not in _STATIC_INR_RATES or to_currency not in _STATIC_INR_RATES:
        raise ValueError(f"Unsupported currency (static table only covers {sorted(_STATIC_INR_RATES)})")
    amount_in_inr = amount * _STATIC_INR_RATES[from_currency]
    converted = amount_in_inr / _STATIC_INR_RATES[to_currency]
    return {
        "amount": amount, "from": from_currency, "to": to_currency,
        "converted": round(converted, 2),
        "rate_source": "static_reference_table_not_live",
    }


# ---- Domain knowledge-base lookups ---------------------------------------
# Honest framing: these search OUR indexed official sources for that domain
# (Qdrant/jsonl), not a live external government/bank/hospital/insurer API --
# no such API access is configured in this deployment.

async def _domain_lookup(domain: Domain, query: str, top_k: int = 5) -> dict:
    hits = await qdrant_service.search_chunks(domain, query, top_k=top_k)
    return {
        "domain": domain.value,
        "query": query,
        "source": "indexed_official_documents",
        "results": [{"text": h.get("text", "")[:300], "score": h.get("score")} for h in hits],
    }


async def government_lookup(query: str) -> dict:
    return await _domain_lookup(Domain.GOVERNMENT, query)


async def hospital_lookup(query: str) -> dict:
    return await _domain_lookup(Domain.HEALTHCARE, query)


async def bank_lookup(query: str) -> dict:
    return await _domain_lookup(Domain.BANKING, query)


async def insurance_lookup(query: str) -> dict:
    return await _domain_lookup(Domain.HEALTH_INSURANCE, query)


# ---- Web search (delegates to the existing Tavily-backed service) --------

async def web_search(query: str, max_results: int = 5) -> dict:
    from app.services.web_search import web_search_service
    results = await web_search_service.search(query, max_results=max_results)
    return {"query": query, "results": results}


def register_builtin_tools() -> None:
    tool_registry.register("calculator", "Evaluate an arithmetic expression (+ - * / ** %).", calculator)
    tool_registry.register("date_diff", "Days between two ISO dates.", date_diff)
    tool_registry.register("date_add", "Add/subtract days from an ISO date.", date_add)
    tool_registry.register("today", "Today's date.", today)
    tool_registry.register("pdf_parser", "Extract text from a PDF/text file on disk.", pdf_parser)
    tool_registry.register("currency_conversion", "Convert between currencies (static reference rates, not live).", currency_conversion)
    tool_registry.register("government_lookup", "Search indexed official Indian government sources.", government_lookup)
    tool_registry.register("hospital_lookup", "Search indexed public-health/hospital-quality sources.", hospital_lookup)
    tool_registry.register("bank_lookup", "Search indexed RBI/banking official sources.", bank_lookup)
    tool_registry.register("insurance_lookup", "Search indexed health insurance policy/regulatory sources.", insurance_lookup)
    tool_registry.register("web_search", "Live web search (Tavily-backed) for current information.", web_search)


register_builtin_tools()
