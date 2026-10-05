"""Offline coastline/border rendering and view controls for the v4 canvas."""

from functools import lru_cache
import json
import math
from pathlib import Path


def project(lon, lat, width, height, bounds):
    west, east, south, north = bounds
    return ((lon - west) / (east - west) * (width - 1),
            (north - lat) / (north - south) * (height - 1))


def load_lines(filename):
    with Path(__file__).with_name(filename).open(encoding="utf-8") as stream:
        data = json.load(stream)
    lines = tuple(tuple(tuple(point) for point in line) for line in data["lines"])
    if not lines or any(len(p) != 2 or not all(isinstance(v, (int, float))
                                             and math.isfinite(v) for v in p)
                        for line in lines for p in line):
        raise ValueError("Invalid map coordinates")
    return lines


@lru_cache(maxsize=1)
def load_coastlines():
    return load_lines("world_coastlines.json")


@lru_cache(maxsize=1)
def load_borders():
    return load_lines("world_borders.json")


def clip_line(x0, y0, x1, y1, width, height):
    """Clip before rasterizing, including lines with both endpoints offscreen."""
    dx, dy = x1 - x0, y1 - y0
    start, end = 0.0, 1.0
    for p, q in ((-dx, x0), (dx, width - 1 - x0),
                 (-dy, y0), (dy, height - 1 - y0)):
        if p == 0:
            if q < 0:
                return None
        else:
            ratio = q / p
            if p < 0:
                start = max(start, ratio)
            else:
                end = min(end, ratio)
            if start > end:
                return None
    return tuple(round(v) for v in (
        x0 + start * dx, y0 + start * dy, x0 + end * dx, y0 + end * dy))


def line_points(x0, y0, x1, y1):
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx + dy
    while True:
        yield x0, y0
        if (x0, y0) == (x1, y1):
            break
        twice = error * 2
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


@lru_cache(maxsize=8)
def coastline_texture(width, height, bounds):
    """Natural Earth outlines at 2 by 4 dots per Braille character."""
    return lines_texture(load_coastlines(), width, height, bounds)


@lru_cache(maxsize=8)
def border_texture(width, height, bounds):
    return lines_texture(load_borders(), width, height, bounds)


def lines_texture(lines, width, height, bounds):
    cells = [[0] * width for _ in range(height)]
    pixel_w, pixel_h = width * 2, height * 4
    bits = ((1, 8), (2, 16), (4, 32), (64, 128))
    for line in lines:
        for a, b in zip(line, line[1:]):
            if abs(a[0] - b[0]) > 180:
                continue  # Do not join opposite edges of the world.
            endpoints = clip_line(*project(*a, pixel_w, pixel_h, bounds),
                                  *project(*b, pixel_w, pixel_h, bounds), pixel_w, pixel_h)
            if endpoints is not None:
                for x, y in line_points(*endpoints):
                    cells[y // 4][x // 2] |= bits[y % 4][x % 2]
    return tuple("".join(chr(0x2800 + v) if v else " " for v in row) for row in cells)


class MapViewport:
    def __init__(self, bounds):
        self.base_bounds = bounds
        self.reset()

    def reset(self):
        west, east, south, north = self.base_bounds
        self.longitude, self.latitude = (west + east) / 2, (south + north) / 2
        self.zoom = 1.0

    @property
    def bounds(self):
        west, east, south, north = self.base_bounds
        half_w, half_h = (east - west) / (2 * self.zoom), (north - south) / (2 * self.zoom)
        return (self.longitude - half_w, self.longitude + half_w,
                self.latitude - half_h, self.latitude + half_h)

    def _clamp_center(self):
        west, east, south, north = self.bounds
        half_w, half_h = (east - west) / 2, (north - south) / 2
        self.longitude = max(-180 + half_w, min(180 - half_w, self.longitude))
        self.latitude = max(-85 + half_h, min(85 - half_h, self.latitude))

    def zoom_by(self, factor):
        self.zoom = max(1.0, min(8.0, self.zoom * factor))
        self._clamp_center()

    def pan(self, dx, dy):
        west, east, south, north = self.bounds
        self.longitude += dx * (east - west) * 0.12
        self.latitude -= dy * (north - south) * 0.12
        self._clamp_center()

    def ease_out(self, dt):
        """Gradually return to this region's overview, without crossing 1x."""
        if self.zoom <= 1 or dt <= 0:
            return
        old_zoom = self.zoom
        self.zoom = max(1.0, self.zoom * math.exp(-0.18 * dt))
        west, east, south, north = self.base_bounds
        fraction = (old_zoom - self.zoom) / (old_zoom - 1)
        self.longitude += ((west + east) / 2 - self.longitude) * fraction
        self.latitude += ((south + north) / 2 - self.latitude) * fraction
        self._clamp_center()
