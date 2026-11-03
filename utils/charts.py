"""Expense charts rendered with matplotlib (Agg backend, no GUI) and returned as PNG bytes.

Only the object-oriented API is used (no pyplot), so rendering holds no global state and is safe to run
in a worker thread via `asyncio.to_thread`. The bundled DejaVu Sans font covers Latin, Cyrillic and the
Uzbek letters; characters the font cannot draw (emoji, for instance) are dropped from labels instead of
producing "missing glyph" warnings.
"""
import io
from functools import lru_cache
from typing import List, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "DejaVu Sans"

from matplotlib import font_manager  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

FONT = "DejaVu Sans"
MAX_DONUT_SLICES = 8  # more categories than this are drawn as horizontal bars
MAX_BARS = 9  # biggest categories shown as bars; the rest are summed into "Other"
SMALL_SHARE = 0.03  # donut slices below this share are merged into "Other"
RING_WIDTH = 0.38  # donut ring width (the pie radius is 1)
HOLE_FILL = 0.86  # the centre text may use this share of the hole's diameter
CENTER_FONT = 13  # largest centre font size; it shrinks down to MIN_CENTER_FONT to fit
MIN_CENTER_FONT = 7
# Distinguishable on white, colour-blind friendly (Okabe-Ito based); "Other" is grey
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#7A5195", "#8C564B"]
OTHER_COLOR = "#9AA0A6"

Item = Tuple[str, int]


@lru_cache(maxsize=1)
def _font_path() -> str:
    return font_manager.findfont(font_manager.FontProperties(family=FONT), fallback_to_default=True)


@lru_cache(maxsize=1)
def _font_face():
    from matplotlib import ft2font

    return ft2font.FT2Font(_font_path())


def printable(label: str) -> str:
    """Drop characters that the chart font has no glyph for (e.g. emoji, variation selectors)."""
    face = _font_face()
    kept = "".join(ch for ch in label if ch.isspace() or face.get_char_index(ord(ch)) != 0)
    return " ".join(kept.split())


def group_items(items: Sequence[Item], other_label: str, donut: bool) -> List[Item]:
    """Sort by amount and fold the tail into one "Other" entry (bars: beyond MAX_BARS, donut: tiny slices)."""
    ordered = sorted((i for i in items if i[1] > 0), key=lambda item: -item[1])
    total = sum(value for _, value in ordered)
    if not total:
        return []
    if donut:
        main = [i for i in ordered if i[1] / total >= SMALL_SHARE]
        tail = [i for i in ordered if i[1] / total < SMALL_SHARE]
        if len(tail) < 2:  # a single small slice keeps its own name
            main, tail = ordered, []
    else:
        main, tail = ordered[:MAX_BARS], ordered[MAX_BARS:]
    if tail:
        main = main + [(other_label, sum(value for _, value in tail))]
    return main


def center_lines(total_text: str) -> str:
    """'Total: 2 440 000 UZS' -> 'Total:' over '2 440 000 UZS' (a label and an amount never share a line)."""
    label, sep, amount = total_text.partition(": ")
    return f"{label}:\n{amount}" if sep and amount else total_text


def _draw_donut(fig: Figure, items: List[Item], colors: List[str], total_text: str):
    """Draw the donut; returns (axes, centre text) so the text can be fitted once the layout is final."""
    ax = fig.add_subplot(111)
    values = [value for _, value in items]
    shares = [value / sum(values) * 100 for value in values]
    wedges, _ = ax.pie(values, colors=colors, startangle=90, counterclock=False,
                       wedgeprops={"width": RING_WIDTH, "edgecolor": "white", "linewidth": 1.5})
    center = ax.text(0, 0, center_lines(printable_lines(total_text)), ha="center", va="center",
                     fontsize=CENTER_FONT, fontweight="bold", color="#202124", linespacing=1.15)
    ax.set_aspect("equal")
    labels = [f"{printable(name) or '—'}  " + ("<1%" if share < 1 else f"{share:.0f}%")
              for (name, _), share in zip(items, shares)]
    ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=11)
    return ax, center


def printable_lines(text: str) -> str:
    return "\n".join(printable(line) for line in text.split("\n"))


def hole_size(ax) -> float:
    """Diameter of the donut hole in display pixels (with the final layout and equal aspect applied)."""
    ax.apply_aspect()
    radius = 1 - RING_WIDTH
    (x0, _), (x1, _) = ax.transData.transform([(-radius, 0), (radius, 0)])
    return abs(x1 - x0)


def fit_center_text(fig: Figure, ax, text) -> None:
    """Shrink the centre text until its box fits inside the hole (checked on width and height)."""
    renderer = fig.canvas.get_renderer()
    limit = hole_size(ax) * HOLE_FILL
    size = CENTER_FONT
    while size > MIN_CENTER_FONT:
        box = text.get_window_extent(renderer)
        # the box must fit in the circle: its diagonal is the binding dimension
        if (box.width ** 2 + box.height ** 2) ** 0.5 <= limit:
            return
        size -= 0.5
        text.set_fontsize(size)


def _draw_bars(fig: Figure, items: List[Item], colors: List[str], value_fmt) -> None:
    ax = fig.add_subplot(111)
    names = [printable(name) or "—" for name, _ in items]
    values = [value for _, value in items]
    positions = list(range(len(items)))
    ax.barh(positions, values, color=colors, height=0.65)
    ax.set_yticks(positions)
    ax.set_yticklabels(names, fontsize=11)
    ax.invert_yaxis()
    top = max(values)
    for pos, value in zip(positions, values):
        ax.text(value + top * 0.01, pos, value_fmt(value), va="center", fontsize=10, color="#202124")
    ax.set_xlim(0, top * 1.28)
    ax.xaxis.set_visible(False)
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#BDC1C6")
    ax.tick_params(axis="y", length=0)


def build_expense_figure(items: Sequence[Item], title: str, total_text: str, other_label: str,
                         amount_text) -> Figure:
    """The chart figure (see render_expense_chart)."""
    donut = len([i for i in items if i[1] > 0]) <= MAX_DONUT_SLICES
    grouped = group_items(items, other_label, donut)
    if not grouped:
        raise ValueError("no expenses to draw")
    colors = [OTHER_COLOR if name == other_label else PALETTE[i % len(PALETTE)]
              for i, (name, _) in enumerate(grouped)]
    height = 4.6 if donut else max(3.6, 0.5 * len(grouped) + 1.6)
    fig = Figure(figsize=(8, height), dpi=130, facecolor="white")
    FigureCanvasAgg(fig)
    fig.suptitle(printable(title), fontsize=14, fontweight="bold", x=0.02, ha="left", color="#202124")
    if donut:
        ax, center = _draw_donut(fig, grouped, colors, total_text)
        fig.subplots_adjust(left=0.02, right=0.62, top=0.88, bottom=0.04)
        fit_center_text(fig, ax, center)
    else:
        _draw_bars(fig, grouped, colors, amount_text)
        fig.subplots_adjust(left=0.30, right=0.97, top=0.88, bottom=0.04)
    return fig


def render_expense_chart(items: Sequence[Item], title: str, total_text: str, other_label: str,
                         amount_text) -> bytes:
    """PNG of expenses by category: a donut for up to 8 categories, horizontal bars for more.

    items: (category, minor units); amount_text(minor) -> short label used on bars; total_text is shown in
    the donut's centre ("Label: amount" is split into two lines and the font shrinks to fit the hole).
    Raises ValueError if there is nothing to draw.
    """
    fig = build_expense_figure(items, title, total_text, other_label, amount_text)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor="white")
    return buffer.getvalue()
