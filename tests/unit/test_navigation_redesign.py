from qx.ui.pages import PAGES
from qx.ui.streamlit_app import PAGE_GROUPS, PAGE_ROUTE_ALIASES, PAGE_ROUTE_TABS


def test_every_page_has_exactly_one_home() -> None:
    assigned = [title for titles in PAGE_GROUPS.values() for title in titles]
    assert len(assigned) == len(set(assigned))
    assert set(assigned) == {page.title for page in PAGES}


def test_legacy_routes_resolve_to_their_page_home() -> None:
    for route, title in PAGE_ROUTE_TABS.items():
        assert title in PAGE_GROUPS[PAGE_ROUTE_ALIASES[route]]
