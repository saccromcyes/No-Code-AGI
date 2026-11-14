import httpx
import pytest

from agentkit.tools import TOOLS, ToolContext, ToolError, safe_eval


@pytest.mark.parametrize(
    "expr, value",
    [
        ("2 + 3 * 4", 14),
        ("10000 * 1.07 ** 10", 10000 * 1.07**10),
        ("0.175 * 2,340", 409.5),
        ("sqrt(16) + max(1, 2)", 6),
        ("2^10", 1024),
        ("1969 - 1889", 80),
    ],
)
def test_safe_eval(expr, value):
    assert safe_eval(expr) == pytest.approx(value)


@pytest.mark.parametrize(
    "expr", ["__import__('os').system('ls')", "open('/etc/passwd')", "(1).__class__", "9 ** 9 ** 9", "a + 1", "lambda: 1"]
)
def test_safe_eval_rejects_code(expr):
    with pytest.raises(ToolError):
        safe_eval(expr)


def run(name, args, settings, **ctx):
    return TOOLS[name].fn(ToolContext(settings, **ctx), args)


def test_calculator_formats_integers(settings):
    assert run("calculator", {"expression": "1969 - 1889"}, settings) == "1969 - 1889 = 80"


def test_date_math(settings):
    assert "Saturday" in run("date_math", {"operation": "add_days", "date": "2026-01-01", "days": 100}, settings)
    assert "286 days" in run(
        "date_math", {"operation": "days_between", "date": "2026-03-14", "other_date": "2026-12-25"}, settings
    )
    with pytest.raises(ToolError):
        run("date_math", {"operation": "weekday", "date": "14/03/2026"}, settings)


def test_current_time_rejects_bad_zone(settings):
    assert "Asia/Kolkata" in run("current_time", {"timezone": "Asia/Kolkata"}, settings)
    with pytest.raises(ToolError):
        run("current_time", {"timezone": "Mars/Base"}, settings)


def test_search_notes_returns_best_passage(settings):
    notes = "Bikes can be returned within 30 days.\n\nFrames have a lifetime warranty.\n\nTune-ups cost $79."
    out = run("search_notes", {"query": "frame warranty"}, settings, notes=notes)
    assert "lifetime warranty" in out
    assert "no notes" in run("search_notes", {"query": "x"}, settings).lower()


def test_read_webpage_blocks_private_addresses(settings):
    for url in ("http://127.0.0.1:8000/", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd", "http://10.1.2.3/"):
        with pytest.raises(ToolError):
            run("read_webpage", {"url": url}, settings)


def test_wikipedia_tools_with_mocked_api(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("list") == "search":
            return httpx.Response(
                200, json={"query": {"search": [{"title": "Eiffel Tower", "snippet": "wrought-<b>iron</b> tower"}]}}
            )
        return httpx.Response(200, json={"query": {"pages": [{"title": "Eiffel Tower", "extract": "Completed in 1889."}]}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert "Eiffel Tower: wrought-iron tower" in run("wikipedia_search", {"query": "eiffel"}, settings, http=client)
    assert "1889" in run("wikipedia_article", {"title": "Eiffel Tower"}, settings, http=client)


def test_every_tool_has_a_valid_schema():
    for tool in TOOLS.values():
        schema = tool.schema()
        assert schema["function"]["name"] == tool.name
        assert schema["function"]["parameters"]["type"] == "object"
