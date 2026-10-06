"""WCAG 2.2 contrast checks for the proposed ResearchConnect AI token palette (light and dark)."""
from __future__ import annotations


def lum(hex_: str) -> float:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


LIGHT = {
    "bg": "#F7F6F3", "surface": "#FFFFFF", "sunken": "#F0EEE9",
    "border": "#E2DED6", "border-strong": "#8A8478",
    "text": "#1B1A18", "text-2": "#47443F", "text-3": "#615D56",
    "brand": "#0E6B66", "brand-hover": "#0A5450", "brand-subtle": "#E7F2F0", "brand-text": "#0B5C57",
    "focus": "#0E6B66",
    "info": "#1D5A9E", "info-subtle": "#E8F0FA",
    "success": "#1B6E3F", "success-subtle": "#E6F3EA",
    "warning": "#8A5300", "warning-subtle": "#FBF1DC",
    "danger": "#B42318", "danger-subtle": "#FCEBE9",
    "deadline-urgent": "#A33F07", "deadline-urgent-subtle": "#FCEEE3",
    "match-strong-fill": "#0E6B66", "match-good-text": "#0B5C57", "match-good-fill": "#DCEEEA",
}
DARK = {
    "bg": "#111315", "surface": "#181B1E", "sunken": "#0D0F10", "raised": "#1F2327",
    "border": "#2C3136", "border-strong": "#6B737B",
    "text": "#ECEAE6", "text-2": "#C4BFB6", "text-3": "#A19C93",
    "brand": "#5FBDB3", "brand-fill": "#1F7A72", "brand-subtle": "#14302D", "brand-text": "#7FCFC6",
    "focus": "#7FCFC6",
    "info": "#8AB8EC", "info-subtle": "#14263A",
    "success": "#7CCB98", "success-subtle": "#132A1C",
    "warning": "#E8B65C", "warning-subtle": "#2E2311",
    "danger": "#F19A90", "danger-subtle": "#341614",
    "deadline-urgent": "#F2A26B", "deadline-urgent-subtle": "#33200F",
    "match-good-text": "#7FCFC6", "match-good-fill": "#173733",
}

CHECKS = [
    # (foreground, background, minimum, purpose)
    ("text", "bg", 4.5, "body text on page"), ("text", "surface", 4.5, "body text on card"),
    ("text-2", "bg", 4.5, "secondary text on page"), ("text-2", "surface", 4.5, "secondary text on card"),
    ("text-3", "bg", 4.5, "muted metadata on page"), ("text-3", "surface", 4.5, "muted metadata on card"),
    ("text-3", "sunken", 4.5, "muted text on sunken panel"),
    ("brand-text", "surface", 4.5, "links and brand text on card"), ("brand-text", "bg", 4.5, "links on page"),
    ("brand-text", "brand-subtle", 4.5, "selected nav item / brand chip"),
    ("info", "info-subtle", 4.5, "info badge"), ("success", "success-subtle", 4.5, "success badge"),
    ("warning", "warning-subtle", 4.5, "warning badge"), ("danger", "danger-subtle", 4.5, "danger badge"),
    ("deadline-urgent", "deadline-urgent-subtle", 4.5, "urgent deadline chip"),
    ("deadline-urgent", "surface", 4.5, "urgent deadline text on card"),
    ("danger", "surface", 4.5, "error text on card"), ("warning", "surface", 4.5, "warning text on card"),
    ("match-good-text", "match-good-fill", 4.5, "good match badge"),
    ("border-strong", "surface", 3.0, "input border (non-text, 1.4.11)"),
    ("focus", "surface", 3.0, "focus ring on card (2.4.13 / 1.4.11)"), ("focus", "bg", 3.0, "focus ring on page"),
]


def run(name: str, pal: dict[str, str]) -> int:
    failures = 0
    print(f"\n== {name}")
    for fg, bg, minimum, purpose in CHECKS:
        if fg not in pal or bg not in pal:
            continue
        r = ratio(pal[fg], pal[bg])
        ok = r >= minimum
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'} {r:5.2f}:1 (min {minimum}) {fg:24} on {bg:22} {purpose}")
    # Button text on brand fills.
    fills = [("#FFFFFF", pal.get("brand"), "white on brand button")] if name == "light" else [("#0D0F10", pal.get("brand"), "near-black on brand button"), ("#FFFFFF", pal.get("brand-fill"), "white on brand fill")]
    if name == "light":
        fills += [("#FFFFFF", pal["brand-hover"], "white on brand hover"), ("#FFFFFF", pal["danger"], "white on danger button"), ("#FFFFFF", pal["match-strong-fill"], "white on strong match")]
    for fg, bg, purpose in fills:
        r = ratio(fg, bg)
        ok = r >= 4.5
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'} {r:5.2f}:1 (min 4.5) {purpose}")
    return failures


bad = run("light", LIGHT) + run("dark", DARK)
print("\nOLD palette spot checks (current app):")
for fg, bg, what in (("#94a3b8", "#ffffff", "--text-subtle on white"), ("#64748b", "#f8fafc", "--text-muted on --bg-app"),
                     ("#a5b4fc", "#eef2ff", "calendar event text (approx.)"), ("#ffffff", "#0f766e", "white on --primary"),
                     ("#ffffff", "#3b82f6", "white on calendar blue button"), ("#0f766e", "#f0fdf4", "--primary on --primary-subtle")):
    print(f"  {ratio(fg, bg):5.2f}:1  {what}")
print("\nTOTAL FAILURES:", bad)
