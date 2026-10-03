from pdf2muse.review import build_score_review_html, playback_events_from_musicxml

XML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration></note>
    </measure>
  </part>
</score-partwise>
"""


def test_playback_events_include_midi():
    events = playback_events_from_musicxml(XML)
    assert events
    assert events[0]["midi"] == 60


def test_review_html_embeds_osmd_iframe():
    html = build_score_review_html(XML, page_image_data_uri="data:image/png;base64,aaa")
    assert "opensheetmusicdisplay" in html
    assert "srcdoc=" in html
    assert "Play draft" in html
