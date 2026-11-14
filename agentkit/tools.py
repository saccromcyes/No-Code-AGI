"""The tools an agent can be given. Each tool has a JSON schema (sent to the model) and a Python
function. Tools never raise: failures come back as an error string the model can react to."""

from __future__ import annotations

import ast
import datetime as dt
import ipaddress
import math
import operator
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from rank_bm25 import BM25Okapi

from agentkit.config import Settings


class ToolError(Exception):
    """An error the model should see and can recover from."""


@dataclass
class ToolContext:
    settings: Settings
    notes: str = ""
    http: httpx.Client | None = None


@dataclass
class Tool:
    name: str
    label: str
    description: str  # for the model
    summary: str  # for people, shown in the builder
    parameters: dict
    fn: Callable[[ToolContext, dict], str]

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


# ---------------------------------------------------------------- calculator
_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "floor": math.floor,
    "ceil": math.ceil,
}
_CONSTS = {"pi": math.pi, "e": math.e}


def safe_eval(expression: str) -> float:
    """Evaluate arithmetic without eval(): only numbers, operators and whitelisted functions."""
    if len(expression) > 300:
        raise ToolError("Expression too long.")
    # "2,340" -> "2340" (thousands separators), but keep commas between function arguments.
    expression = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", expression).replace("^", "**")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1e6):
                raise ToolError("Exponent too large.")
            return _BIN[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Name) and node.id in _CONSTS:
            return _CONSTS[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise ToolError(f"Unsupported syntax: {ast.dump(node)[:60]}")

    try:
        return ev(ast.parse(expression.strip(), mode="eval"))
    except ToolError:
        raise
    except ZeroDivisionError as exc:
        raise ToolError("Division by zero.") from exc
    except (SyntaxError, TypeError, ValueError, OverflowError) as exc:
        raise ToolError(f"Could not evaluate: {exc}") from exc


def _calculator(ctx: ToolContext, args: dict) -> str:
    result = safe_eval(str(args.get("expression", "")))
    if isinstance(result, float):
        result = round(result, 10)
        if result.is_integer():
            result = int(result)
    return f"{args.get('expression')} = {result}"


# ---------------------------------------------------------------- dates
def _date_math(ctx: ToolContext, args: dict) -> str:
    op = args.get("operation")
    try:
        start = dt.date.fromisoformat(str(args.get("date")))
    except ValueError as exc:
        raise ToolError("`date` must be YYYY-MM-DD.") from exc
    if op == "weekday":
        return f"{start.isoformat()} is a {start.strftime('%A')}."
    if op == "add_days":
        days = int(args.get("days", 0))
        if abs(days) > 100_000:
            raise ToolError("`days` is too large.")
        out = start + dt.timedelta(days=days)
        return f"{start.isoformat()} + {days} days = {out.isoformat()} ({out.strftime('%A')})."
    if op == "days_between":
        try:
            end = dt.date.fromisoformat(str(args.get("other_date")))
        except ValueError as exc:
            raise ToolError("`other_date` must be YYYY-MM-DD.") from exc
        return f"There are {(end - start).days} days from {start.isoformat()} to {end.isoformat()}."
    raise ToolError("`operation` must be weekday, add_days or days_between.")


def _now(ctx: ToolContext, args: dict) -> str:
    tz_name = args.get("timezone") or "UTC"
    try:
        now = dt.datetime.now(ZoneInfo(tz_name))
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ToolError(f"Unknown time zone '{tz_name}'. Use an IANA name such as Asia/Kolkata.") from exc
    return f"It is {now.strftime('%A %Y-%m-%d %H:%M')} in {tz_name}."


# ---------------------------------------------------------------- web
def _check_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ToolError("Only http and https URLs are allowed.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ToolError("That host could not be found.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ToolError("That address is not allowed.")


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in {"p", "div", "li", "br", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t\r\f\v]+", " ", "".join(p.parts))).strip()


def _read_webpage(ctx: ToolContext, args: dict) -> str:
    url = str(args.get("url", "")).strip()
    client = ctx.http or httpx.Client(timeout=ctx.settings.tool_timeout_s)
    for _ in range(4):
        _check_public(url)  # checked on every redirect hop
        resp = client.get(url, follow_redirects=False, headers={"User-Agent": ctx.settings.user_agent})
        if resp.is_redirect and resp.headers.get("location"):
            url = urljoin(url, resp.headers["location"])
            continue
        if resp.status_code >= 400:
            raise ToolError(f"The page returned HTTP {resp.status_code}.")
        text = html_to_text(resp.text) if "html" in resp.headers.get("content-type", "") else resp.text
        return f"Text of {url}:\n{text}"
    raise ToolError("Too many redirects.")


def _wiki(ctx: ToolContext, params: dict) -> dict:
    client = ctx.http or httpx.Client(timeout=ctx.settings.tool_timeout_s)
    resp = client.get(
        ctx.settings.wikipedia_api,
        params={**params, "format": "json", "formatversion": 2},
        headers={"User-Agent": ctx.settings.user_agent},
    )
    if resp.status_code != 200:
        raise ToolError(f"Wikipedia returned HTTP {resp.status_code}.")
    return resp.json()


def _wikipedia_search(ctx: ToolContext, args: dict) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("`query` is required.")
    data = _wiki(ctx, {"action": "query", "list": "search", "srsearch": query, "srlimit": 5})
    hits = data.get("query", {}).get("search", [])
    if not hits:
        return f"No Wikipedia articles found for '{query}'."
    lines = [f"- {h['title']}: {re.sub(r'<[^>]+>', '', h.get('snippet', ''))}" for h in hits]
    return "Top Wikipedia articles:\n" + "\n".join(lines)


def _wikipedia_article(ctx: ToolContext, args: dict) -> str:
    title = str(args.get("title", "")).strip()
    if not title:
        raise ToolError("`title` is required.")
    data = _wiki(ctx, {"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1, "titles": title})
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        raise ToolError(f"No article titled '{title}'. Search first to find the exact title.")
    return f"Wikipedia: {pages[0]['title']}\n{pages[0].get('extract', '')}"


# ---------------------------------------------------------------- notes
_WORD = re.compile(r"[a-z0-9]+")


def _search_notes(ctx: ToolContext, args: dict) -> str:
    if not ctx.notes.strip():
        return "This agent has no notes."
    passages = [p.strip() for p in re.split(r"\n\s*\n", ctx.notes) if p.strip()]
    query = _WORD.findall(str(args.get("query", "")).lower())
    if not query:
        raise ToolError("`query` is required.")
    tokens = [_WORD.findall(p.lower()) or ["_"] for p in passages]
    # BM25 IDF goes to zero or below when a term is in most passages (always, with 1-2 passages),
    # so rank by how many query words a passage contains and use BM25 only to break ties.
    bm25 = BM25Okapi(tokens)
    scores = bm25.get_scores(query)
    overlap = [len(set(query) & set(t)) for t in tokens]
    ranked = sorted(range(len(passages)), key=lambda i: (overlap[i], scores[i]), reverse=True)[:3]
    hits = [passages[i] for i in ranked if overlap[i] > 0]
    if not hits:
        return "Nothing in the notes matches that query."
    return "Matching notes:\n" + "\n---\n".join(hits)


# ---------------------------------------------------------------- registry
TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "calculator",
            "Calculator",
            "Evaluate an arithmetic expression exactly. Use for any arithmetic instead of mental math. "
            "Supports + - * / // % ** and sqrt, log, exp, round, min, max, pi, e.",
            "Exact arithmetic, so the agent never does maths in its head.",
            {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "e.g. 10000 * 1.07 ** 10"}},
                "required": ["expression"],
            },
            _calculator,
        ),
        Tool(
            "date_math",
            "Date maths",
            "Calendar arithmetic: the weekday of a date, a date plus N days, or days between two dates.",
            "Weekdays, adding days, and days between dates.",
            {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["weekday", "add_days", "days_between"]},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "days": {"type": "integer", "description": "for add_days"},
                    "other_date": {"type": "string", "description": "YYYY-MM-DD, for days_between"},
                },
                "required": ["operation", "date"],
            },
            _date_math,
        ),
        Tool(
            "current_time",
            "Current time",
            "Get the current date and time, optionally in an IANA time zone.",
            "Today's date and time in any time zone.",
            {"type": "object", "properties": {"timezone": {"type": "string", "description": "e.g. Asia/Kolkata"}}},
            _now,
        ),
        Tool(
            "wikipedia_search",
            "Wikipedia search",
            "Search Wikipedia and return the top article titles with snippets.",
            "Find relevant Wikipedia articles.",
            {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            _wikipedia_search,
        ),
        Tool(
            "wikipedia_article",
            "Wikipedia article",
            "Read the plain text of a Wikipedia article by its exact title.",
            "Read a Wikipedia article in full.",
            {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
            _wikipedia_article,
        ),
        Tool(
            "read_webpage",
            "Read a web page",
            "Fetch a public web page and return its readable text.",
            "Read any public web page by URL.",
            {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            _read_webpage,
        ),
        Tool(
            "search_notes",
            "Search my notes",
            "Search the notes the agent's builder attached and return the best-matching passages.",
            "Look things up in the notes you give the agent.",
            {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            _search_notes,
        ),
    ]
}
