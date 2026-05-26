"""
KMZ export — layered, color-coded visualization of a survey route.

Layers produced:
  AI Spatial Analysis
    1. Street Width polygons (continuous trapezoid between consecutive points)
    2. Wall Height bars (3D extruded lines, left=red, right=blue)
    3. H/W Ratio polygons (color-coded by enclosure depth)
    4. Observation points with embedded thumbnails + AI metadata balloon

  Environmental Sensors (one sub-folder per dataset_name)
    5. Temperature (°C)        — colored trajectory + min/max stars
    6. Humidity (%)            — colored trajectory + min/max stars
    7. Lux                     — colored trajectory + min/max stars
    8. UV Index                — colored trajectory + min/max stars

Each colored layer ships with a ScreenOverlay legend so the KMZ is
self-explanatory in Google Earth without any external CSS.

Adapted from the original KMZEngine — schema mapping:
  pt.street_width_m      ← analysis.walkway_width_m
  pt.left.wall_height_m  ← analysis.urban_morphology["building_height_est_m"]
  pt.right.wall_height_m ← same (project schema has one building height per side)
  pt.hw_effective_avg    ← analysis.urban_morphology["height_width_ratio"]
  pt.image_id            ← os.path.basename(analysis.image_path)
  pt.sensor_data         ← joined SensorReading rows (separate layer, not per-point)
"""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass
from typing import Iterable, Optional

import simplekml
from PIL import Image, ImageDraw, ImageFont

from app.models import SensorReading, StreetAnalysis, SurveyRoute


# ── Color palettes (ABGR for KML) ──────────────────────────────

def _hw_color(hw: Optional[float]) -> str:
    if hw is None:
        return "8878b159"
    if hw < 0.5:
        return "ff78b159"  # green — open
    if hw < 1.0:
        return "ff78f3fd"  # yellow
    if hw < 2.0:
        return "ff4db7ff"  # orange
    return "ff4370ff"      # red — deep canyon


def _temp_color(v: Optional[float]) -> str:
    if v is None: return "00ffffff"
    if v < 28: return "ffc9e6c8"
    if v < 32: return "ffb8f3fd"
    if v < 36: return "ff4db7ff"
    return "ff4370ff"


def _humid_color(v: Optional[float]) -> str:
    if v is None: return "00ffffff"
    if v < 50: return "ffe0f2fe"
    if v < 70: return "ffbae6fd"
    if v < 85: return "ff38bdf8"
    return "ff0369a1"


def _lux_color(v: Optional[float]) -> str:
    if v is None: return "00ffffff"
    if v < 1000: return "ff23273e"
    if v < 7000: return "ff636e8d"
    if v < 30000: return "ffc4f9ff"
    return "ff2dc0fb"


def _uv_color(v: Optional[float]) -> str:
    if v is None: return "00ffffff"
    if v < 3: return "ff22c55e"
    if v < 6: return "fffacc15"
    if v < 8: return "fff97316"
    return "ff7c3aed"


# ── Geometry helpers ──────────────────────────────────────────

_EARTH_RADIUS_M = 6378137


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dl = math.radians(lon2 - lon1)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _offset(lat: float, lon: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    br = math.radians(bearing_deg)
    p, l = math.radians(lat), math.radians(lon)
    d = dist_m / _EARTH_RADIUS_M
    new_p = math.asin(math.sin(p) * math.cos(d) + math.cos(p) * math.sin(d) * math.cos(br))
    new_l = l + math.atan2(
        math.sin(br) * math.sin(d) * math.cos(p),
        math.cos(d) - math.sin(p) * math.sin(new_p),
    )
    return math.degrees(new_p), math.degrees(new_l)


# ── Analysis field extraction (defensive against missing JSONB keys) ──

def _morph(a: StreetAnalysis, key: str, default=None):
    m = a.urban_morphology or {}
    val = m.get(key, default)
    return val if val not in ("unknown", "", None) else default


def _wall_height(a: StreetAnalysis) -> float:
    h = _morph(a, "building_height_est_m") or _morph(a, "building_height")
    try:
        return float(h) if h is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _hw_ratio(a: StreetAnalysis) -> Optional[float]:
    h = _morph(a, "height_width_ratio")
    try:
        return float(h) if h is not None else None
    except (TypeError, ValueError):
        return None


def _enclosure_class(hw: Optional[float]) -> str:
    if hw is None: return "unknown"
    if hw < 0.5: return "open"
    if hw < 1.0: return "moderate"
    if hw < 2.0: return "compact"
    return "deep canyon"


# ── Legend rendering ──────────────────────────────────────────

@dataclass
class LegendItem:
    color: str  # ABGR
    label: str


def _legend_png(title: str, items: list[LegendItem], out_path: str) -> None:
    w = 200
    h = 30 + len(items) * 25 + 10
    img = Image.new("RGBA", (w, h), (255, 255, 255, 220))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((10, 8), title, fill=(40, 40, 40, 255), font=font)
    draw.line([(10, 25), (w - 10, 25)], fill=(200, 200, 200, 255), width=1)
    y = 35
    for it in items:
        # ABGR → RGB
        b = int(it.color[2:4], 16)
        g = int(it.color[4:6], 16)
        r = int(it.color[6:8], 16)
        draw.rectangle([10, y, 25, y + 15], fill=(r, g, b, 255), outline=(100, 100, 100, 255))
        draw.text((35, y + 2), it.label, fill=(30, 30, 30, 255), font=font)
        y += 25
    img.save(out_path)


def _attach_legend(kml: simplekml.Kml, folder, title: str, items: list[LegendItem], tmp_dir: str, index: int) -> None:
    safe = title.lower().replace(" ", "_").replace("/", "_").replace("°", "").replace("(", "").replace(")", "")
    png_path = os.path.join(tmp_dir, f"legend_{safe}.png")
    _legend_png(title, items, png_path)
    kmz_ref = kml.addfile(png_path)
    y = 0.05 + index * 0.20
    ov = folder.newscreenoverlay(name=f"Legend: {title}")
    ov.icon.href = kmz_ref
    ov.overlayxy = simplekml.OverlayXY(x=1, y=0, xunits=simplekml.Units.fraction, yunits=simplekml.Units.fraction)
    ov.screenxy = simplekml.ScreenXY(x=0.99, y=y, xunits=simplekml.Units.fraction, yunits=simplekml.Units.fraction)
    ov.size = simplekml.Size(x=0, y=0, xunits=simplekml.Units.fraction, yunits=simplekml.Units.fraction)


# ── Sensor segment plotting ────────────────────────────────────

def _plot_sensor_path(
    folder,
    points: list[SensorReading],
    metric_attr: str,
    color_fn,
    export_mode: str,
    unit: str,
) -> None:
    """
    Draw a colored polyline by walking `points` in time order and starting a
    new segment every time the color bucket changes. Optionally overlay
    min/max star markers when export_mode == 'minmax'.
    """
    seg: list[tuple[float, float]] = []
    seg_color: Optional[str] = None

    for i, p in enumerate(points):
        v = getattr(p, metric_attr, None)
        c = color_fn(v)
        coord = (p.longitude, p.latitude)

        if seg_color is None:
            seg = [coord]
            seg_color = c
            continue

        if c == seg_color:
            seg.append(coord)
        else:
            if len(seg) > 1:
                ls = folder.newlinestring(name=f"Segment {i}")
                ls.coords = seg
                ls.style.linestyle.color = seg_color
                ls.style.linestyle.width = 4
            seg = [seg[-1], coord]
            seg_color = c

    if len(seg) > 1 and seg_color:
        ls = folder.newlinestring(name="Final Segment")
        ls.coords = seg
        ls.style.linestyle.color = seg_color
        ls.style.linestyle.width = 4

    if export_mode == "minmax":
        valid = [(i, p) for i, p in enumerate(points) if getattr(p, metric_attr, None) is not None]
        if not valid:
            return
        lo_idx, lo = min(valid, key=lambda x: getattr(x[1], metric_attr))
        hi_idx, hi = max(valid, key=lambda x: getattr(x[1], metric_attr))
        for label, pt in (("min", lo), ("max", hi)) if lo_idx != hi_idx else (("min", lo),):
            val = getattr(pt, metric_attr)
            star = folder.newpoint(name=f"{label.upper()} {val}{unit}", coords=[(pt.longitude, pt.latitude)])
            star.style.iconstyle.icon.href = "http://maps.google.com/mapfiles/kml/shapes/star.png"
            star.style.iconstyle.color = color_fn(val)
            star.style.iconstyle.scale = 1.2
            star.description = f"<b>{label.upper()}</b><br><b>Time:</b> {pt.recorded_at}<br><b>{metric_attr}:</b> {val}{unit}"


# ── Main entry point ───────────────────────────────────────────

def build_route_kmz(
    route: SurveyRoute,
    analyses: list[StreetAnalysis],
    sensor_readings: list[SensorReading],
    out_path: str,
    enabled_sensors: Optional[dict[str, bool]] = None,
    export_mode: str = "all",
) -> str:
    """
    Build a KMZ file for a survey route. Returns the output path.

    enabled_sensors: {"temp": True, "humid": True, "lux": True, "uv": True}
    export_mode: "all" (full colored path) or "minmax" (path + star markers)
    """
    if enabled_sensors is None:
        enabled_sensors = {"temp": True, "humid": True, "lux": True, "uv": True}

    tmp_dir = tempfile.mkdtemp(prefix="kmz_")
    kml = simplekml.Kml()

    # ── AI Spatial folders ────────────────────────────────────
    f_ai = kml.newfolder(name="AI Spatial Analysis")
    f_width = f_ai.newfolder(name="1. Street Width (Polygon)")
    f_walls = f_ai.newfolder(name="2. Wall Heights (3D Bars)")
    f_hw = f_ai.newfolder(name="3. H/W Ratio")
    f_obs = f_ai.newfolder(name="4. Observation Points")

    valid = [a for a in analyses if a.geom is not None]
    _draw_ai_layers(kml, valid, f_width, f_walls, f_hw, f_obs)

    if valid:
        _attach_legend(
            kml, f_hw, "H/W Ratio",
            [
                LegendItem("ff78b159", "< 0.5 (Open)"),
                LegendItem("ff78f3fd", "0.5 – 1.0"),
                LegendItem("ff4db7ff", "1.0 – 2.0"),
                LegendItem("ff4370ff", ">= 2.0 (Deep)"),
            ],
            tmp_dir, index=0,
        )

    # ── Sensor folders (one sub-folder per dataset) ──────────
    if sensor_readings:
        f_sensor = kml.newfolder(name="Environmental Sensors")
        by_ds: dict[str, list[SensorReading]] = {}
        for r in sensor_readings:
            by_ds.setdefault(r.dataset_name, []).append(r)

        sensor_specs = [
            ("temp", "Temperature (°C)", "temp_c", _temp_color, "°C"),
            ("humid", "Humidity (%)", "humidity_pct", _humid_color, "%"),
            ("lux", "Lux (Light)", "lux", _lux_color, ""),
            ("uv", "UV Index", "uv_index", _uv_color, ""),
        ]

        for legend_idx, (key, title, attr, color_fn, unit) in enumerate(sensor_specs, start=1):
            if not enabled_sensors.get(key):
                continue
            folder = f_sensor.newfolder(name=f"{legend_idx + 4}. {title}")
            folder.visibility = 0
            for ds_name, pts in by_ds.items():
                sub = folder.newfolder(name=f"Dataset: {ds_name}")
                _plot_sensor_path(sub, pts, attr, color_fn, export_mode, unit)
            _attach_legend(kml, folder, title, _legend_items_for(key), tmp_dir, index=legend_idx)

    kml.savekmz(out_path)
    return out_path


def _legend_items_for(key: str) -> list[LegendItem]:
    if key == "temp":
        return [
            LegendItem("ffc9e6c8", "< 28 °C"),
            LegendItem("ffb8f3fd", "28 – 32 °C"),
            LegendItem("ff4db7ff", "32 – 36 °C"),
            LegendItem("ff4370ff", ">= 36 °C"),
        ]
    if key == "humid":
        return [
            LegendItem("ffe0f2fe", "< 50 %"),
            LegendItem("ffbae6fd", "50 – 70 %"),
            LegendItem("ff38bdf8", "70 – 85 %"),
            LegendItem("ff0369a1", ">= 85 %"),
        ]
    if key == "lux":
        return [
            LegendItem("ff23273e", "< 1k (dark)"),
            LegendItem("ff636e8d", "1k – 7k"),
            LegendItem("ffc4f9ff", "7k – 30k"),
            LegendItem("ff2dc0fb", ">= 30k (bright)"),
        ]
    return [
        LegendItem("ff22c55e", "< 3 (low)"),
        LegendItem("fffacc15", "3 – 6 (moderate)"),
        LegendItem("fff97316", "6 – 8 (high)"),
        LegendItem("ff7c3aed", ">= 8 (very high)"),
    ]


def _draw_ai_layers(
    kml: simplekml.Kml,
    points: list[StreetAnalysis],
    f_width, f_walls, f_hw, f_obs,
) -> None:
    """Draw all AI-derived layers for the route in one pass."""
    for i, pt in enumerate(points):
        lat, lon = pt.latitude, pt.longitude
        width = pt.walkway_width_m or 0
        if width <= 0:
            continue
        half = width / 2

        is_last = i == len(points) - 1
        if not is_last:
            nxt = points[i + 1]
            bearing = _bearing(lat, lon, nxt.latitude, nxt.longitude)
        elif i > 0:
            prev = points[i - 1]
            bearing = _bearing(prev.latitude, prev.longitude, lat, lon)
        else:
            bearing = 0

        left_b = (bearing - 90 + 360) % 360
        right_b = (bearing + 90) % 360
        l_lat, l_lon = _offset(lat, lon, left_b, half)
        r_lat, r_lon = _offset(lat, lon, right_b, half)

        # Width + H/W polygons (only if next point exists)
        if not is_last:
            nxt = points[i + 1]
            n_half = (nxt.walkway_width_m or 0) / 2
            nl_lat, nl_lon = _offset(nxt.latitude, nxt.longitude, left_b, n_half)
            nr_lat, nr_lon = _offset(nxt.latitude, nxt.longitude, right_b, n_half)
            coords = [
                (l_lon, l_lat),
                (r_lon, r_lat),
                (nr_lon, nr_lat),
                (nl_lon, nl_lat),
                (l_lon, l_lat),
            ]
            pw = f_width.newpolygon(name=f"Width #{pt.id}")
            pw.outerboundaryis = coords
            pw.style.polystyle.color = "8878b159"
            pw.style.linestyle.width = 0

            hw = _hw_ratio(pt)
            phw = f_hw.newpolygon(name=f"H/W #{pt.id}")
            phw.outerboundaryis = coords
            phw.style.polystyle.color = _hw_color(hw)
            phw.style.linestyle.width = 1

        # Wall bars (3D extruded lines)
        wh = _wall_height(pt)
        if wh > 0:
            bl = f_walls.newlinestring(name=f"L-Wall #{pt.id}")
            bl.coords = [(l_lon, l_lat, 0), (l_lon, l_lat, wh)]
            bl.altitudemode = simplekml.AltitudeMode.relativetoground
            bl.extrude = 1
            bl.style.linestyle.color = "ffff0000"
            bl.style.linestyle.width = 5

            br = f_walls.newlinestring(name=f"R-Wall #{pt.id}")
            br.coords = [(r_lon, r_lat, 0), (r_lon, r_lat, wh)]
            br.altitudemode = simplekml.AltitudeMode.relativetoground
            br.extrude = 1
            br.style.linestyle.color = "ff0000ff"
            br.style.linestyle.width = 5

        # Observation point with image thumbnail
        op = f_obs.newpoint(name=f"#{pt.id}", coords=[(lon, lat)])
        op.description = _build_observation_html(kml, pt)


def _build_observation_html(kml: simplekml.Kml, pt: StreetAnalysis) -> str:
    """Build the popup balloon HTML for a single analysis point."""
    width = pt.walkway_width_m
    hw = _hw_ratio(pt)
    wh = _wall_height(pt)
    enc = _enclosure_class(hw)

    img_block = ""
    if pt.image_path and os.path.isfile(pt.image_path):
        try:
            opt_path = _make_thumbnail(pt.image_path)
            kmz_ref = kml.addfile(opt_path)
            img_block = f'<img src="{kmz_ref}" style="width:100%;border-radius:5px;margin-top:10px;"/>'
        except Exception:
            pass

    note = pt.scene_description or ""
    note_block = (
        f'<div style="margin-top:8px;padding:8px;background:#f8f9fa;'
        f'border-left:3px solid #1a73e8;font-size:11px;font-style:italic;">{note}</div>'
        if note else ""
    )

    return f"""
    <div style="font-family:Arial,sans-serif;width:300px;">
      <h3 style="color:#1a73e8;border-bottom:1px solid #eee;">Observation #{pt.id}</h3>
      <table style="width:100%;font-size:12px;">
        <tr><td><b>Street Width:</b></td><td>{width or '–'} m</td></tr>
        <tr><td><b>Wall Height:</b></td><td>{wh or '–'} m</td></tr>
        <tr><td><b>H/W Ratio:</b></td><td>{hw if hw is not None else '–'}</td></tr>
        <tr><td><b>Enclosure:</b></td><td>{enc}</td></tr>
      </table>
      {note_block}
      {img_block}
    </div>
    """


def _make_thumbnail(src_path: str) -> str:
    """Generate a 640x480 JPEG thumbnail next to the original. Idempotent."""
    base = os.path.basename(src_path)
    dst_dir = os.path.dirname(src_path)
    dst = os.path.join(dst_dir, f"opt_{base}")
    if os.path.exists(dst):
        return dst
    with Image.open(src_path) as img:
        img.thumbnail((640, 480))
        img.convert("RGB").save(dst, "JPEG", quality=75)
    return dst
