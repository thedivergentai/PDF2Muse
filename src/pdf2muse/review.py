"""OSMD review HTML plus a tiny playback event list."""

from __future__ import annotations

import html
import json
import xml.etree.ElementTree as ET
from typing import Any, Optional

from .midiutil import midi_from_step
from .musicxml import _child_text, _findall_local, _find_local, _local_name


def playback_events_from_musicxml(musicxml_text: str) -> list[dict[str, Any]]:
    """Extract a coarse {midi, start, duration} list for in-browser preview."""

    events: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(musicxml_text)
    except ET.ParseError:
        return events

    for part in [el for el in root if _local_name(el.tag) == "part"]:
        cursor = 0.0
        divisions = 1.0
        for measure in _findall_local(part, "measure"):
            attrs = _find_local(measure, "attributes")
            if attrs is not None:
                div_text = _child_text(attrs, "divisions")
                if div_text:
                    try:
                        divisions = float(div_text)
                    except ValueError:
                        pass
            for child in list(measure):
                name = _local_name(child.tag)
                if name == "backup":
                    dur = _child_text(child, "duration")
                    if dur:
                        cursor -= float(dur) / divisions
                    continue
                if name == "forward":
                    dur = _child_text(child, "duration")
                    if dur:
                        cursor += float(dur) / divisions
                    continue
                if name != "note":
                    continue
                dur_text = _child_text(child, "duration")
                duration = float(dur_text) / divisions if dur_text else 0.25
                if _find_local(child, "chord") is None:
                    start = cursor
                    cursor += duration
                else:
                    start = cursor - duration
                if _find_local(child, "rest") is not None:
                    continue
                pitch_el = _find_local(child, "pitch")
                if pitch_el is None:
                    continue
                step = _child_text(pitch_el, "step")
                octave = _child_text(pitch_el, "octave")
                alter_text = _child_text(pitch_el, "alter")
                if not step or octave is None:
                    continue
                try:
                    alter = int(float(alter_text)) if alter_text else 0
                    events.append(
                        {
                            "midi": midi_from_step(step, int(octave), alter),
                            "start": round(start, 4),
                            "duration": round(duration, 4),
                        }
                    )
                except (KeyError, ValueError, TypeError):
                    continue
    return events


def build_score_review_html(
    musicxml_text: str,
    *,
    page_image_data_uri: Optional[str] = None,
    playback_events: Optional[list[dict[str, Any]]] = None,
) -> str:
    """iframe srcdoc: original page | OSMD | Play button."""

    events = playback_events if playback_events is not None else playback_events_from_musicxml(
        musicxml_text
    )
    xml_js = json.dumps(musicxml_text)
    events_js = json.dumps(events)
    image_block = ""
    if page_image_data_uri:
        image_block = (
            f'<div class="pane"><h3>Original page</h3>'
            f'<img alt="Original page" src="{html.escape(page_image_data_uri, quote=True)}" />'
            f"</div>"
        )
    srcdoc = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8" />
<style>
  body {{ margin: 0; font-family: Inter, system-ui, sans-serif; background: #1c1917; color: #fafaf9; }}
  .row {{ display: flex; gap: 12px; padding: 12px; align-items: stretch; }}
  .pane {{ flex: 1; min-width: 0; background: #292524; border-radius: 12px; padding: 12px; }}
  img {{ max-width: 100%; height: auto; background: white; }}
  #osmd {{ min-height: 280px; background: white; border-radius: 8px; }}
  button {{ min-height: 44px; padding: 0 16px; border: 0; border-radius: 8px;
            background: linear-gradient(135deg, #ea580c, #f97316); color: white; font-weight: 600; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/opensheetmusicdisplay@1.8.9/build/opensheetmusicdisplay.min.js"></script>
</head><body>
<div class="row">
  {image_block}
  <div class="pane">
    <h3>Recognized draft</h3>
    <p>Draft only — listen, then edit in MuseScore before performance or teaching.</p>
    <button type="button" id="play">Play draft</button>
    <div id="osmd"></div>
  </div>
</div>
<script>
const MUSICXML = {xml_js};
const EVENTS = {events_js};
const osmd = new opensheetmusicdisplay.OpenSheetMusicDisplay("osmd", {{ autoResize: true, drawTitle: true }});
osmd.load(MUSICXML).then(() => osmd.render());
document.getElementById("play").onclick = async () => {{
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const now = ctx.currentTime + 0.05;
  for (const ev of EVENTS) {{
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 440 * Math.pow(2, (ev.midi - 69) / 12);
    gain.gain.value = 0.12;
    osc.connect(gain); gain.connect(ctx.destination);
    osc.start(now + ev.start * 0.5);
    osc.stop(now + (ev.start + Math.max(0.1, ev.duration)) * 0.5);
  }}
}};
</script>
</body></html>"""
    escaped = html.escape(srcdoc, quote=True)
    return (
        '<iframe title="Score review" style="width:100%;height:640px;border:0;'
        f'border-radius:12px;background:#1c1917" srcdoc="{escaped}"></iframe>'
    )
