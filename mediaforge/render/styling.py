"""Frame styling — CSS generation from FrameStyle declarations.

Converts FrameStyle dataclass objects into CSS variables and rules
that are injected into Hyperframes HTML templates.

Includes a Squircle SVG filter generator (iOS-style continuous curve corners)
inspired by Recordly's getSquirclePathPoints() algorithm.
"""

from __future__ import annotations

from mediaforge.types import FrameStyle


def style_to_css(style: FrameStyle) -> str:
    """Generate CSS from a FrameStyle for injection into HTML templates.

    Returns a <style> block with CSS variables and body rules.
    """
    css_parts = [":root {"]

    # Background
    if style.background_type == "gradient" and style.gradient_colors:
        css_parts.append(
            f"  --mf-bg: linear-gradient({style.gradient_angle}deg, "
            f"{', '.join(style.gradient_colors)});"
        )
    else:
        css_parts.append(f"  --mf-bg: {style.background_color};")

    # Frame geometry
    css_parts.append(f"  --mf-radius: {style.border_radius}px;")
    css_parts.append(f"  --mf-padding: {style.padding}px;")

    # Shadow
    if style.shadow_enabled:
        css_parts.append(
            f"  --mf-shadow: {style.shadow_offset_x}px {style.shadow_offset_y}px "
            f"{style.shadow_blur}px {style.shadow_color};"
        )
    else:
        css_parts.append("  --mf-shadow: none;")

    # Blur (not supported via CSS variable alone in static context; applied by engine)
    css_parts.append(f"  --mf-blur: {style.background_blur}px;")

    css_parts.append("}")

    # Body rules
    css_parts.append("body.mf-styled {")
    css_parts.append(f"  background: var(--mf-bg);")
    if style.border_radius > 0:
        css_parts.append(f"  border-radius: var(--mf-radius);")
    if style.shadow_enabled:
        css_parts.append(f"  box-shadow: var(--mf-shadow);")
    if style.background_blur > 0:
        css_parts.append(
            f"  backdrop-filter: blur(var(--mf-blur));"
        )
        css_parts.append(
            f"  -webkit-backdrop-filter: blur(var(--mf-blur));"
        )
    css_parts.append("}")

    return "\n".join(css_parts)


def squircle_svg_filter(width: int, height: int, radius: int) -> str:
    """Generate an SVG clipPath for squircle (continuous-curve) corners.

    Uses the Lamé curve approximation: |x/a|^n + |y/b|^n = 1 with n=4.
    This produces iOS-style rounded corners that are smoother than CSS
    border-radius, which uses circular arcs.

    Inspired by Recordly's getSquirclePathPoints() — the same geometric
    algorithm but output as SVG clipPath instead of FFmpeg PGM mask.

    Args:
        width: SVG viewport width.
        height: SVG viewport height.
        radius: Corner radius in px (0 = no squircle).

    Returns:
        SVG string with a <clipPath id="squircle-clip"> element.
    """
    if radius <= 0:
        return ""

    # Generate squircle path using Lamé curve parametric equation
    # x(t) = a * |cos(t)|^(2/n) * sign(cos(t))
    # y(t) = b * |sin(t)|^(2/n) * sign(sin(t))
    # with n=4 for the classic squircle look
    import math

    n = 4.0
    a = width / 2.0
    b = height / 2.0
    steps = 64

    points = []
    for i in range(steps):
        t = (i / steps) * 2 * math.pi
        cos_t = math.cos(t)
        sin_t = math.sin(t)

        x = a * (abs(cos_t) ** (2 / n)) * (1 if cos_t >= 0 else -1) + a
        y = b * (abs(sin_t) ** (2 / n)) * (1 if sin_t >= 0 else -1) + b

        # Scale radius: apply as offset from corners
        if radius > 0:
            # Lerp: scale coordinates toward center by radius factor
            cx, cy = a, b  # center
            scale = 1.0 - (radius / min(a, b))
            x = cx + (x - cx) * scale
            y = cy + (y - cy) * scale

        points.append(f"{x:.2f},{y:.2f}")

    path_d = f"M {points[0]} " + " L ".join(points[1:]) + " Z"

    return (
        f'<svg width="0" height="0" style="position:absolute">'
        f"<defs>"
        f'<clipPath id="squircle-clip" clipPathUnits="objectBoundingBox">'
        f'<path d="{path_d}" '
        f'transform="scale({1/width}, {1/height})" '
        f'clip-rule="evenodd"/>'
        f"</clipPath>"
        f"</defs>"
        f"</svg>"
    )


def build_style_html(style: FrameStyle) -> str:
    """Build CSS variables + optional SVG for injection into <style> block.

    Returns raw CSS (no <style> wrapper) — the caller is responsible for
    injecting this inside an existing <style> block.
    """
    css = style_to_css(style)
    result = css

    if style.use_squircle and style.border_radius > 0:
        w, h = _get_aspect_dims(style.aspect_ratio)
        result += "\n" + squircle_svg_filter(w, h, style.border_radius)

    return result


def _get_aspect_dims(aspect_ratio: str) -> tuple[int, int]:
    """Resolve aspect ratio name to dimensions."""
    from mediaforge.types import ASPECT_RATIOS

    return ASPECT_RATIOS.get(aspect_ratio, (1920, 1080))
