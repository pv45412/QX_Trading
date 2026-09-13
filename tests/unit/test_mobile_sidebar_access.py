"""Keep essential Streamlit chrome accessible in both style injection paths."""

from importlib import import_module
from pathlib import Path
import re
import runpy
import sys
from types import SimpleNamespace
from typing import Any, Iterator

from bs4 import BeautifulSoup
import pytest

from qx.ui.app_shell import inject_app_styles
from qx.ui import app_shell


@pytest.fixture(params=["html", "markdown"])
def app_css(request: pytest.FixtureRequest) -> str:
    calls: list[str] = []

    def markdown(body: str, *, unsafe_allow_html: bool = False) -> None:
        assert unsafe_allow_html
        calls.append(body)

    app = SimpleNamespace(markdown=markdown)
    if request.param == "html":
        app.html = calls.append
    inject_app_styles(app)
    assert len(calls) == 1
    return BeautifulSoup(calls[0], "html.parser").style.get_text()


def _rules(css: str) -> list[tuple[str, dict[str, str]]]:
    # Only leaf declaration blocks are relevant, including rules inside media queries.
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return [
        (
            selector.strip(),
            {
                name.strip(): value.strip().removesuffix("!important").strip()
                for declaration in body.split(";")
                if ":" in declaration
                for name, value in [declaration.split(":", 1)]
            },
        )
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        for selector in selectors.split(",")
    ]


def _declarations(css: str, selector: str) -> dict[str, str]:
    return {
        name: value
        for rule, values in _rules(css)
        if rule == selector
        for name, value in values.items()
    }


@pytest.mark.parametrize(
    "markup",
    [
        '<header data-testid="stHeader"><div data-testid="stToolbar">'
        '<div><button data-testid="stExpandSidebarButton"></button></div></div></header>',
        '<div data-testid="stSidebarCollapsedControl"><button></button></div>',
        '<section data-testid="stSidebar" aria-expanded="true">'
        '<div data-testid="stSidebarContent"><div data-testid="stSidebarHeader">'
        '<div data-testid="stSidebarCollapseButton"><button></button></div>'
        '</div></div></section>',
    ],
    ids=["toolbar-reopen", "legacy-reopen", "sidebar-close"],
)
def test_shell_never_hides_sidebar_toggle_or_its_ancestors(app_css: str, markup: str) -> None:
    tree = BeautifulSoup(markup, "html.parser")
    for selector, declarations in _rules(app_css):
        if "::" in selector:
            continue
        if tree.select(selector):
            assert declarations.get("display") != "none", selector
            assert declarations.get("visibility") not in {"hidden", "collapse"}, selector
            assert declarations.get("height") not in {"0", "0px"}, selector
            assert declarations.get("opacity") != "0", selector
            assert declarations.get("pointer-events") != "none", selector


@pytest.mark.parametrize(
    "test_id",
    ["stToolbar", "stExpandSidebarButton", "stSidebarCollapsedControl", "stSidebarCollapseButton"],
)
def test_sidebar_toggle_visibility_does_not_require_hover(app_css: str, test_id: str) -> None:
    declarations = _declarations(app_css, f'[data-testid="{test_id}"]')
    assert declarations["display"] == "flex"
    assert declarations["visibility"] == "visible"


@pytest.mark.parametrize(
    "selector",
    [
        '[data-testid="stExpandSidebarButton"]',
        '[data-testid="stSidebarCollapsedControl"] button',
        '[data-testid="stSidebarCollapseButton"] button',
    ],
)
def test_sidebar_toggle_has_touch_target_and_keyboard_focus(app_css: str, selector: str) -> None:
    declarations = _declarations(app_css, selector)
    assert declarations["min-width"] == "max(44px, 2.75rem)"
    assert declarations["min-height"] == "max(44px, 2.75rem)"
    assert dict(_rules(app_css))[selector + ":focus-visible"]["outline"].startswith("2px solid")


@pytest.mark.parametrize(
    "selector",
    [
        ".stAppDeployButton",
        ".stDeployButton",
        '[data-testid="stToolbarActions"]',
        '[data-testid="stHeaderActionElements"]',
        '[data-testid="stSidebarNav"]',
        '[data-testid="stDecoration"]',
        '[data-testid="stStatusWidget"]',
        "#MainMenu",
    ],
)
def test_nonessential_chrome_stays_hidden(app_css: str, selector: str) -> None:
    declarations = dict(_rules(app_css))[selector]
    assert declarations["display"] == "none"
    assert declarations["visibility"] == "hidden"


@pytest.fixture
def standalone_probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "mobile_sidebar_import_probe.py"
    path.write_text(
        'from qx.ui.app_shell import run_standalone_page\n'
        'def render_page(streamlit):\n'
        '    streamlit.caption("Probe rendered")\n'
        'run_standalone_page("Probe", "Standalone caption", render_page)\n',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    assert path.stem not in sys.modules
    try:
        yield path
    finally:
        sys.modules.pop(path.stem, None)


@pytest.fixture
def standalone_app(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list[tuple[str, Any]]]:
    from streamlit.runtime import scriptrunner

    calls: list[tuple[str, Any]] = []
    app = SimpleNamespace(
        set_page_config=lambda **kwargs: calls.append(("config", kwargs)),
        html=lambda body: calls.append(("styles", body)),
        markdown=lambda body, **kwargs: calls.append(("markdown", body)),
        caption=lambda body: calls.append(("caption", body)),
    )
    monkeypatch.setattr(scriptrunner, "get_script_run_ctx", lambda: object())
    monkeypatch.setattr(
        app_shell, "import_module",
        lambda name: app if name == "streamlit" else import_module(name),
    )
    return app, calls


def test_first_page_import_does_not_render_in_active_streamlit_context(
    standalone_probe: Path, standalone_app: tuple[Any, list[tuple[str, Any]]],
) -> None:
    app, calls = standalone_app

    module = import_module(standalone_probe.stem)

    assert calls == []
    module.render_page(app)
    assert calls == [("caption", "Probe rendered")]


def test_lazy_renderer_renders_first_import_only_once_without_process_global_state(
    standalone_probe: Path, standalone_app: tuple[Any, list[tuple[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    app, calls = standalone_app
    monkeypatch.setenv("SCANNER_SUPPRESS_NATIVE_PAGE_RENDER", "owned-by-another-caller")

    app_shell.lazy_page_renderer(standalone_probe.stem, "render_page")(app)

    assert calls == [("caption", "Probe rendered")]
    assert os.environ["SCANNER_SUPPRESS_NATIVE_PAGE_RENDER"] == "owned-by-another-caller"


def test_native_main_page_renders_header_and_body_once(
    standalone_probe: Path, standalone_app: tuple[Any, list[tuple[str, Any]]],
) -> None:
    _, calls = standalone_app

    runpy.run_path(str(standalone_probe), run_name="__main__")

    assert [kind for kind, _ in calls] == ["config", "styles", "markdown", "caption"]
    assert calls[0][1] == {"page_title": "Probe", "layout": "wide"}
    assert '<h1>Probe</h1>' in calls[2][1]
    assert calls[-1] == ("caption", "Probe rendered")


def test_native_main_page_without_streamlit_context_does_not_render(
    standalone_probe: Path, standalone_app: tuple[Any, list[tuple[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.runtime import scriptrunner

    _, calls = standalone_app
    monkeypatch.setattr(scriptrunner, "get_script_run_ctx", lambda: None)

    runpy.run_path(str(standalone_probe), run_name="__main__")

    assert calls == []


def test_first_import_in_apptest_does_not_duplicate_explicit_render(standalone_probe: Path) -> None:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string(
        "import streamlit as st\n"
        f"from {standalone_probe.stem} import render_page\n"
        "render_page(st)\n"
    ).run()

    assert not app.exception
    assert [caption.value for caption in app.caption] == ["Probe rendered"]
    assert not app.markdown


def test_standalone_file_in_apptest_renders_once(standalone_probe: Path) -> None:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(standalone_probe)).run()

    assert not app.exception
    assert [caption.value for caption in app.caption] == ["Probe rendered"]
    assert len(app.markdown) == 1
    assert '<h1>Probe</h1>' in app.markdown[0].value
