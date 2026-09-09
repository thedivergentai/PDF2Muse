from pathlib import Path

from pdf2muse.layout import detect_systems, page_needs_deskew, render_staff_fixture


def test_detects_two_piano_systems(tmp_path: Path):
    image = render_staff_fixture(tmp_path / "page.png", systems=2, staves_per_system=2)
    systems = detect_systems(image)
    assert len(systems) == 2
    assert all(system.staff_count == 2 for system in systems)


def test_aligned_page_skips_deskew(tmp_path: Path):
    image = render_staff_fixture(tmp_path / "aligned.png")
    assert page_needs_deskew(image) is False
