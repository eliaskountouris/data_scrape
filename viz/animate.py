"""Manim scenes that share the matplotlib palette.

manim is an optional dependency (``pip install -e '.[manim]'``); importing this
module without it raises a clear error rather than failing obscurely at render
time. Render with::

    manim -qh viz/animate.py SomeScene

Keeping the colors in :mod:`viz.theme` means an animation and a static chart of
the same data are the same chart.
"""

from __future__ import annotations

from common.paths import MEDIA_ROOT

from .theme import DARK, Theme

try:
    from manim import Scene, config  # type: ignore
except ModuleNotFoundError as exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "viz.animate needs manim: pip install -e '.[manim]'"
    ) from exc


class ThemedScene(Scene):
    """Scene pre-wired to the toolkit palette.

    Video is a dark medium, so the dark theme is the default here -- same hues
    as the light charts, stepped for a dark surface.
    """

    theme: Theme = DARK

    def setup(self) -> None:
        super().setup()
        config.background_color = self.theme.surface
        # Keep rendered video out of the repo root, alongside every other
        # generated file.
        config.media_dir = str(MEDIA_ROOT)

    def series_color(self, i: int) -> str:
        """Categorical slot ``i``, matching the static charts exactly."""
        return self.theme.slot(i)
