"""Synthetic HOMR-style XML; no copyrighted score data or model downloads."""
import xml.etree.ElementTree as ET


from pdf2muse.rhythm_repair import repair_measure_durations
from pdf2muse.header_lock import lock_musicxml_header


def score(content):
    return '<score-partwise><part-list/><part id="P1">'+content+'</part></score-partwise>'


def test_all_attributes_and_inherited_meter(tmp_path):
    path=tmp_path/'split.musicxml'
    path.write_text(score('''<measure number="1"><attributes><divisions>24</divisions></attributes>
    <attributes><key><fifths>-5</fifths></key><time><beats>4</beats><beat-type>2</beat-type></time></attributes>
    <note><pitch><step>C</step><alter>1</alter><octave>5</octave></pitch><duration>192</duration></note></measure>
    <measure number="2"><note><rest/><duration>192</duration></note></measure>'''))
    report=repair_measure_durations(path)
    assert not report.flags and not report.changed
    header=lock_musicxml_header(path)
    assert 'noop_no_key' not in header.actions
    assert ET.parse(path).findtext('.//pitch/step')=='D'
    assert ET.parse(path).findtext('.//pitch/alter')=='-1'


def test_empty_compressed_rest_is_preserved_but_real_underfull_is_flagged(tmp_path):
    path=tmp_path/'rests.musicxml'
    original=score('''<measure number="1"><attributes><divisions>24</divisions></attributes>
    <attributes><time><beats>4</beats><beat-type>2</beat-type></time><measure-style><multiple-rest>3</multiple-rest></measure-style></attributes></measure>
    <measure number="2"><note><rest/><duration>96</duration></note></measure>''')
    path.write_text(original)
    report=repair_measure_durations(path,fill_underfull=False)
    assert [(f.measure_number,f.expected) for f in report.flags]==[('2',192)]
    assert report.rests_appended==0 and not report.changed
    assert path.read_text()==original
    assert 'skip_multimeasure_rest:P1:1' in report.actions


def test_locked_header_has_no_later_override(tmp_path):
    path=tmp_path/'lock.musicxml'
    path.write_text(score('''<measure number="1"><attributes><divisions>24</divisions></attributes>
    <attributes><key><fifths>-5</fifths></key><time><beats>4</beats><beat-type>2</beat-type></time></attributes></measure>'''))
    lock_musicxml_header(path,mode='lock')
    root=ET.parse(path)
    assert len(root.findall('.//time'))==1
    assert root.findtext('.//time/beats')=='4'
    assert len(root.findall('.//key'))==1


def test_fill_rest_notation_matches_divisions(tmp_path):
    path=tmp_path/'fill.musicxml'
    path.write_text(score('''<measure number="1"><attributes><divisions>24</divisions>
    <time><beats>4</beats><beat-type>4</beat-type></time></attributes>
    <note><rest/><duration>24</duration><type>quarter</type></note></measure>'''))
    report=repair_measure_durations(path,fill_underfull=True)
    n=ET.parse(path).findall('.//note')[-1]
    assert report.rests_appended==1
    assert n.findtext('duration')=='72'
    assert n.findtext('type')=='half' and len(n.findall('dot'))==1


def test_underfull_is_reported_without_modification_by_default(tmp_path):
    path = tmp_path / 'underfull.musicxml'
    original = score('''<measure number="24"><attributes><divisions>24</divisions>
    <time><beats>4</beats><beat-type>4</beat-type></time></attributes>
    <note><rest/><duration>12</duration><type>eighth</type></note>
    <note><rest/><duration>12</duration><type>eighth</type></note>
    <note><pitch><step>D</step><octave>4</octave></pitch><duration>12</duration><type>eighth</type></note></measure>''')
    path.write_text(original)
    report = repair_measure_durations(path)
    assert report.rests_appended == 0 and not report.changed
    assert [(f.measure_number, f.actual, f.expected) for f in report.flags] == [('24', 36, 96)]
    assert path.read_text() == original


def test_cli_rest_filling_requires_explicit_opt_in(tmp_path):
    from unittest.mock import patch
    from typer.testing import CliRunner
    from pdf2muse.cli import app
    pdf = tmp_path / 'score.pdf'
    pdf.write_bytes(b'%PDF-placeholder')
    for flags, expected in [([], False), (['--fill-underfull'], True)]:
        with patch('pdf2muse.cli.PDF2MusePipeline') as pipeline:
            pipeline.return_value.run.return_value = tmp_path / 'result.musicxml'
            result = CliRunner().invoke(app, ['convert', str(pdf), *flags])
            assert result.exit_code == 0, result.stdout
            assert pipeline.call_args.kwargs['fill_underfull'] is expected
