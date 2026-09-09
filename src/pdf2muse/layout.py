"""Page layout helpers: staff/system crops and cheap deskew skip."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


@dataclass(frozen=True)
class StaffBox:
    y0: int
    y1: int
    x0: int
    x1: int

    @property
    def height(self) -> int:
        return max(1, self.y1 - self.y0)


@dataclass(frozen=True)
class SystemBox:
    staves: tuple[StaffBox, ...]
    y0: int
    y1: int
    x0: int
    x1: int

    @property
    def staff_count(self) -> int:
        return len(self.staves)


def system_crop_enabled() -> bool:
    flag = os.environ.get("PDF2MUSE_SYSTEM_CROP", "1").strip()
    return flag not in {"0", "false", "False"}


def _dark_row_fractions(image: Image.Image, threshold: int = 140) -> list[float]:
    gray = ImageOps.grayscale(image)
    width, height = gray.size
    pixels = gray.load()
    rows: list[float] = []
    for y in range(height):
        dark = 0
        for x in range(0, width, 2):
            if pixels[x, y] < threshold:
                dark += 1
        rows.append(dark / max(1, (width + 1) // 2))
    return rows


def _smooth(values: list[float], radius: int = 1) -> list[float]:
    if radius <= 0:
        return list(values)
    out: list[float] = []
    n = len(values)
    for i in range(n):
        lo = max(0, i - radius)
        hi = min(n, i + radius + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def _peak_rows(fractions: list[float], min_frac: float = 0.18) -> list[int]:
    peaks: list[int] = []
    for i in range(1, len(fractions) - 1):
        if fractions[i] < min_frac:
            continue
        if fractions[i] >= fractions[i - 1] and fractions[i] >= fractions[i + 1]:
            if peaks and i - peaks[-1] <= 2:
                if fractions[i] > fractions[peaks[-1]]:
                    peaks[-1] = i
                continue
            peaks.append(i)
    return peaks


def _cluster_staff_lines(peaks: list[int], image_width: int) -> list[StaffBox]:
    if len(peaks) < 5:
        return []
    gaps = [peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1)]
    typical = sorted(gaps)[len(gaps) // 2] if gaps else 8
    typical = max(3, min(typical, 40))
    staves: list[StaffBox] = []
    current: list[int] = [peaks[0]]
    for peak in peaks[1:]:
        if peak - current[-1] <= typical * 2:
            current.append(peak)
        else:
            if len(current) >= 4:
                pad = max(6, typical)
                staves.append(
                    StaffBox(
                        y0=max(0, current[0] - pad),
                        y1=current[-1] + pad,
                        x0=0,
                        x1=image_width,
                    )
                )
            current = [peak]
    if len(current) >= 4:
        pad = max(6, typical)
        staves.append(
            StaffBox(
                y0=max(0, current[0] - pad),
                y1=current[-1] + pad,
                x0=0,
                x1=image_width,
            )
        )
    return staves


def _group_systems(staves: list[StaffBox], page_height: int) -> list[SystemBox]:
    if not staves:
        return []
    heights = [staff.height for staff in staves]
    typical_height = sorted(heights)[len(heights) // 2]
    gaps = [staves[i + 1].y0 - staves[i].y1 for i in range(len(staves) - 1)]
    positive = [gap for gap in gaps if gap >= 0]
    median_gap = sorted(positive)[len(positive) // 2] if positive else max(12, typical_height // 4)
    split_at = max(median_gap * 1.8, typical_height * 0.45, 24)
    systems: list[list[StaffBox]] = [[staves[0]]]
    for staff in staves[1:]:
        prev = systems[-1][-1]
        gap = staff.y0 - prev.y1
        if gap <= split_at:
            systems[-1].append(staff)
        else:
            systems.append([staff])
    boxes: list[SystemBox] = []
    for group in systems:
        y0 = max(0, group[0].y0)
        y1 = min(page_height, group[-1].y1)
        x0 = min(staff.x0 for staff in group)
        x1 = max(staff.x1 for staff in group)
        boxes.append(SystemBox(staves=tuple(group), y0=y0, y1=y1, x0=x0, x1=x1))
    return boxes


def detect_systems(image_path: Path) -> list[SystemBox]:
    """Return system bounding boxes, or [] when layout is unclear."""

    try:
        with Image.open(image_path) as raw:
            image = raw.convert("RGB")
    except Exception:
        return []
    width, height = image.size
    fractions = _smooth(_dark_row_fractions(image))
    peaks = _peak_rows(fractions)
    staves = _cluster_staff_lines(peaks, width)
    return _group_systems(staves, height)


def page_needs_deskew(image_path: Path) -> bool:
    """Return False when enough horizontal staff lines are already present."""

    systems = detect_systems(image_path)
    staff_count = sum(system.staff_count for system in systems)
    return staff_count < 1


def crop_system(
    image_path: Path,
    system: SystemBox,
    output_path: Path,
    *,
    pad: int = 16,
) -> Path:
    """Write a padded system crop and return the output path."""

    with Image.open(image_path) as raw:
        image = raw.convert("RGB")
        width, height = image.size
        box = (
            max(0, system.x0 - pad),
            max(0, system.y0 - pad),
            min(width, system.x1 + pad),
            min(height, system.y1 + pad),
        )
        cropped = image.crop(box)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(output_path)
    return output_path


def render_staff_fixture(
    path: Path,
    *,
    systems: int = 2,
    staves_per_system: int = 2,
    width: int = 400,
    line_gap: int = 10,
    staff_gap: int = 36,
    system_gap: int = 90,
) -> Path:
    """Draw a synthetic typeset page for layout unit tests."""

    top = 40
    y = top
    blocks = []
    for _ in range(systems):
        staff_ys = []
        for _staff in range(staves_per_system):
            lines = [y + i * line_gap for i in range(5)]
            staff_ys.append(lines)
            y = lines[-1] + staff_gap
        blocks.append(staff_ys)
        y += system_gap - staff_gap
    height = y + 40
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for staff_ys in blocks:
        for lines in staff_ys:
            for line_y in lines:
                draw.line((20, line_y, width - 20, line_y), fill="black", width=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path
