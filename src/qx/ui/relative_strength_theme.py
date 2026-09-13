"""Page-local presentation matching the supplied relative-strength reference."""

from typing import Any


def apply_relative_strength_theme(st: Any) -> None:
    st.markdown('''<style>
    .rs-summary {background:var(--qx-panel);border:1px solid var(--qx-border);border-radius:8px;
      padding:20px;min-height:204px;box-sizing:border-box;}
    .rs-summary-title {font-size:12px;color:var(--qx-muted);font-weight:600;margin-bottom:18px;}
    .rs-summary-row {display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;
      border-bottom:1px solid var(--qx-border);padding:10px 0;font-size:13px;}
    .rs-summary-row:last-child {border:0;}
    .rs-summary-row small {display:block;color:var(--qx-muted);font-size:11px;overflow-wrap:anywhere;}
    .rs-up {color:var(--qx-positive);}.rs-down {color:var(--qx-danger);}
    @media(max-width:700px) {.rs-summary {min-height:0;padding:14px;}.block-container {padding:1rem;}}
    </style>''', unsafe_allow_html=True)
