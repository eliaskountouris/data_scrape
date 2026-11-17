"""viz.day_timeline and the sleep helpers that feed it. No network."""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.health import flatten_datapoints, nightly, stage_segments  # noqa: E402
from viz import charts, render  # noqa: E402
from viz.charts import clock_label, hours_since  # noqa: E402

OFF = "-28800s"


def seg(start, end, kind):
    return {"startTime": start, "startUtcOffset": OFF, "endTime": end,
            "endUtcOffset": OFF, "type": kind}


SLEEP = [{
    "dataSource": {"platform": "FITBIT"},
    "sleep": {
        "interval": {"startTime": "2026-11-16T07:30:00Z", "startUtcOffset": OFF,
                     "endTime": "2026-11-16T15:00:00Z", "endUtcOffset": OFF},
        "type": "STAGES",
        "metadata": {"mainSleep": True},
        "stages": [seg("2026-11-16T07:40:00Z", "2026-11-16T08:10:00Z", "DEEP"),
                   seg("2026-11-16T08:10:00Z", "2026-11-16T09:00:00Z", "LIGHT"),
                   seg("2026-11-16T11:00:00Z", "2026-11-16T11:15:00Z", "DEEP")],
        "summary": {"minutesAsleep": "420", "stagesSummary": [
            {"type": "DEEP", "minutes": "45"}, {"type": "LIGHT", "minutes": "300"},
            {"type": "REM", "minutes": "75"}, {"type": "AWAKE", "minutes": "30"}]},
    },
}]


def test_stage_segments_are_local_and_dated_by_wake_up():
    s = stage_segments(flatten_datapoints(SLEEP, "sleep"), "deep")
    assert list(s["minutes"]) == [30.0, 15.0]
    # 23:40 the evening before, filed under the morning of Nov 16
    assert s.loc[0, "start_local"] == pd.Timestamp("2026-11-15 23:40")
    assert s.loc[0, "night"] == pd.Timestamp("2026-11-16")


def test_nightly_reads_stage_minutes():
    n = nightly(flatten_datapoints(SLEEP, "sleep")).iloc[0]
    assert n["deep_min"] == 45 and n["asleep_min"] == 420
    assert abs(n["deep_share"] - 45 / 420) < 1e-9


def test_hours_since_keeps_pre_midnight_negative():
    h = hours_since(pd.Series([pd.Timestamp("2026-11-15 23:30")]),
                    pd.Series([pd.Timestamp("2026-11-16")]))
    assert h.iloc[0] == -0.5
    assert clock_label(-0.5) == "00:00" and clock_label(-1) == "23:00"
    assert clock_label(26) == "02:00"


def test_day_timeline_renders_both_modes(tmp_path):
    days = pd.to_datetime(["2026-11-01", "2026-11-01", "2026-11-02"])
    sun_days = pd.date_range("2026-11-01", "2026-11-03")

    def draw(fig, theme):
        ax = fig.subplots()
        charts.day_timeline(ax, theme, days, [1.0, 3.0, -0.2], [1.5, 3.1, 0.4],
                            bar_label="deep", lines=[("sunrise", sun_days, [7.5, 6.5, 6.6], None)],
                            behind=(days[[0, 2]], [-0.5, -1.4], [7.0, 8.0]),
                            behind_label="asleep", min_range=(0, 12),
                            overlays=[("missed", days[:1], [2.0], [2.5], "#e87ba4")])
        assert len(ax.patches) == 6
        lo, hi = ax.get_ylim()
        assert lo < hi                       # time runs upward
        assert hi == 12 and lo == -2         # min_range kept, extended for the 22:36 start
        # the background bars sit underneath the foreground ones
        assert max(p.zorder for p in ax.patches[:2]) < min(p.zorder for p in ax.patches[2:])
        labels = [t.get_text() for t in ax.get_legend().get_texts()]
        assert labels == ["asleep", "deep", "missed", "sunrise"]
        assert "clocks change" in [t.get_text() for t in ax.texts]

    written = render(draw, tmp_path / "timeline")
    assert [p.name for p in written] == ["timeline.png", "timeline-dark.png"]


def test_every_render_is_signed_and_dated(tmp_path):
    import datetime as dt

    import matplotlib.pyplot as plt

    from viz.charts import AUTHOR, sign
    from viz.theme import LIGHT

    fig = plt.figure()
    ax = fig.subplots()
    charts.titles(fig, ax, LIGHT, "t", "sub", "Source: x")
    sign(fig, LIGHT, when=dt.date(2026, 11, 17))
    texts = {t.get_text(): t.get_position()[1] for t in fig.texts}
    assert texts[f"{AUTHOR} 2026/11/17"] < texts["Source: x"]   # below the source line
    # house rule: no titles or subtitles are drawn
    assert ax.get_title() == "" and not ax.texts
    assert set(texts) == {"Source: x", f"{AUTHOR} 2026/11/17"}
    plt.close(fig)


def test_legend_entries_capitalise_each_word():
    from viz.charts import legend_case

    assert legend_case("asleep (any stage)") == "Asleep (Any Stage)"
    assert legend_case("sunrise, San Francisco") == "Sunrise, San Francisco"
    assert legend_case("deep sleep, 7-night mean") == "Deep Sleep, 7-night Mean"
    assert legend_case("more expensive than SFO") == "More Expensive Than SFO"


def test_render_capitalises_legends_by_default(tmp_path):
    seen = []

    def draw(fig, theme):
        ax = fig.subplots()
        ax.plot([0, 1], [0, 1], label="inbound arrived late")
        ax.legend()
        seen.append(fig)

    render(draw, tmp_path / "c", modes=("light",))
    texts = [t.get_text() for t in seen[0].axes[0].get_legend().get_texts()]
    assert texts == ["Inbound Arrived Late"]


def test_ramp_runs_light_to_dark_inclusive():
    from viz import ramp

    r = ramp("#ffffff", "#000000", 3)
    assert r == ["#ffffff", "#808080", "#000000"]
    assert ramp("#123456", "#abcdef", 1) == ["#abcdef"]


def test_timeline_lines_take_style_and_can_skip_the_legend(tmp_path):
    days = pd.to_datetime(["2026-11-01", "2026-11-02"])

    def draw(fig, theme):
        ax = fig.subplots()
        charts.day_timeline(
            ax, theme, days, [1.0, 2.0], [1.5, 2.5], bar_label="deep",
            lines=[("solid", days, [8.0, 8.1], None, {"linewidth": 2.4}),
                   (None, days, [8.0, 9.0], None, {"linestyle": ":"}),
                   ("dotted group", days, [7.9, 8.0], None, {"linestyle": ":"})],
            mark_jumps=None, legend_ncol=2)
        assert [ln.get_linestyle() for ln in ax.get_lines()] == ["-", ":", ":"]
        assert [t.get_text() for t in ax.get_legend().get_texts()] == [
            "deep", "solid", "dotted group"]
        assert not ax.texts                                     # no clock-change labels

    render(draw, tmp_path / "styled", modes=("light",))


def test_render_centres_the_plot_area(tmp_path):
    """Long y tick labels on the left must not push the plot off centre."""
    import matplotlib.pyplot as plt

    from viz.charts import centered_bbox

    with plt.rc_context({"savefig.bbox": "tight"}):
        fig = plt.figure(figsize=(8, 5))
        ax = fig.subplots()
        ax.barh(["a very long category label", "b"], [1, 2])
        fig.text(0.0, -0.05, "a source line that runs well past the plot on the left")
        box = centered_bbox(fig, pad=0)
        r = fig.canvas.get_renderer()
        plot = ax.get_window_extent(r).transformed(fig.dpi_scale_trans.inverted())
        left, right = plot.x0 - box.x0, box.x1 - plot.x1
        assert abs(left - right) < 1e-6
        tight = fig.get_tightbbox(r)
        assert box.x0 <= tight.x0 + 1e-9 and box.x1 >= tight.x1 - 1e-9   # nothing cropped
        plt.close(fig)
