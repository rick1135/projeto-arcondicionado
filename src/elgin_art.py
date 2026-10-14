"""Arte do painel Elgin, fiel ao layout gerado pelo Stitch (code.html / screen.png).

Tudo que é estático ou depende de poucos estados (fundo, chassi do aparelho,
fluxo de ar, botões, trilha do slider e cartões) é desenhado aqui com PIL em
supersampling (3×) e depois reduzido, para obter bordas suaves, degradês e
brilhos que o Canvas do Tk não oferece. Textos dinâmicos ficam no Tk.

As coordenadas lógicas são baseadas no viewport padrão de 390 × 844 px.
"""

import math
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter


WIDTH, HEIGHT = 390, 844
SS = 3  # fator de supersampling

TOP_BOX = (0, 0, WIDTH, 360)             # área com energia, aparelho e vento
UNIT_BOX = (25, 126, 365, 222)           # chassi split: 340 × 96, rounded-[18px]
DISPLAY_BOX = (292, 146, 348, 174)       # mini display digital do chassi
WIND_BOX = (25, 220, 365, 345)           # 340 × 125, sob a aleta do chassi
POWER_BOX = (318, 30, 366, 78)           # botão de energia tátil 48 × 48
MINUS_BOX = (28, 488, 76, 536)           # botão [-]
PLUS_BOX = (314, 488, 362, 536)          # botão [+]
TRACK_BOX = (84, 498, 306, 526)          # trilha groove
SLIDER_BOX = (80, 492, 310, 532)         # trilha + margem do brilho
FILL_X, FILL_Y1, FILL_Y2 = 84, 498, 526
THUMB_MIN, THUMB_SPAN = 98, 194          # centro do thumb em 16° e curso até 32°
PLUG_CARD_BOX = (24, 574, 366, 626)      # card integrado da tomada EKAZA
PLUG_ACTION_BOX = (266, 584, 354, 616)   # texto + gap de 6 px + chevron, padding de 12 px
CARD_X0, CARD_STEP, CARD_W = 24, 88.5, 76.5  # 4 colunas fluidas e gutters de 12 px
CARD_Y1, CARD_Y2 = 636, 732
ECO_BOX = (279, 626, 377, 742)           # cartão Eco + margem do brilho neon
FOOTER_LINE_Y = 760
WIND_FRAMES = 14
MIN_TEMP, MAX_TEMP = 16, 32
CARD_ICONS = ("mode", "fan", "extras", "eco")


def rgba(color, alpha=1.0):
    value = color.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16),
            round(alpha * 255))


def card_box(index):
    x1 = CARD_X0 + index * CARD_STEP
    return x1, CARD_Y1, x1 + CARD_W, CARD_Y2


def thumb_x(temperature):
    fraction = (max(MIN_TEMP, min(MAX_TEMP, int(temperature))) - MIN_TEMP) / (MAX_TEMP - MIN_TEMP)
    return THUMB_MIN + fraction * THUMB_SPAN


def temp_from_x(x):
    fraction = max(0.0, min(1.0, (x - THUMB_MIN) / THUMB_SPAN))
    return round(MIN_TEMP + fraction * (MAX_TEMP - MIN_TEMP))


# --------------------------------------------------------------------------
# Primitivas e Operações Gráficas
# --------------------------------------------------------------------------

def composite(dst, src, x, y):
    """alpha_composite com recorte nas bordas do destino."""
    x, y = round(x), round(y)
    sx, sy = max(0, -x), max(0, -y)
    x2, y2 = min(dst.width, x + src.width), min(dst.height, y + src.height)
    if x2 <= x + sx or y2 <= y + sy:
        return
    dst.alpha_composite(src, dest=(x + sx, y + sy), source=(sx, sy, x2 - x, y2 - y))


def with_alpha(layer, factor):
    out = layer.copy()
    out.putalpha(layer.getchannel("A").point(lambda v: round(v * factor)))
    return out


def rr_mask(width, height, radius):
    mask = Image.new("L", (width, height), 0)
    radius = max(0, min(radius, width / 2, height / 2))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1),
                                           radius=radius, fill=255)
    return mask


def gradient(size, stops, horizontal=False):
    """Degradê linear com paradas [(posição 0..1, (r, g, b, a)), ...]."""
    samples = []
    for i in range(256):
        t = i / 255
        c0 = c1 = stops[-1][1]
        f = 0.0
        for (p0, a), (p1, b) in zip(stops, stops[1:]):
            if t <= p1:
                c0, c1 = a, b
                f = 0.0 if p1 == p0 else max(0.0, min(1.0, (t - p0) / (p1 - p0)))
                break
        samples.append(tuple(round(u + (v - u) * f) for u, v in zip(c0, c1)))
    strip = Image.new("RGBA", (256, 1) if horizontal else (1, 256))
    strip.putdata(samples)
    return strip.resize(size, Image.Resampling.BILINEAR)


_TOKEN = re.compile(r"[A-Za-z]|-?(?:\d+\.\d*|\.\d+|\d+)")


def arc_to_points(x0, y0, rx, ry, phi_deg, large_arc, sweep, x1, y1, steps=18):
    """Converte arco elíptico SVG (A/a) para pontos poligonais."""
    if x0 == x1 and y0 == y1:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [(x1, y1)]
    phi = math.radians(phi_deg % 360)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x1) / 2.0, (y0 - y1) / 2.0
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy
    cr = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if cr > 1.0:
        s = math.sqrt(cr)
        rx *= s
        ry *= s
    sign = -1.0 if large_arc == sweep else 1.0
    num = (rx * rx * ry * ry) - (rx * rx * y1p * y1p) - (ry * ry * x1p * x1p)
    den = (rx * rx * y1p * y1p) + (ry * ry * x1p * x1p)
    factor = sign * math.sqrt(max(0.0, num / den)) if den > 0 else 0
    cxp = factor * (rx * y1p / ry)
    cyp = factor * (-ry * x1p / rx)
    cx = cos_phi * cxp - sin_phi * cyp + (x0 + x1) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (y0 + y1) / 2.0

    def vector_angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        length = math.sqrt(ux * ux + uy * uy) * math.sqrt(vx * vx + vy * vy)
        a = math.acos(max(-1.0, min(1.0, dot / length))) if length > 0 else 0
        if ux * vy - uy * vx < 0:
            a = -a
        return a

    theta1 = vector_angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = vector_angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                          (-x1p - cxp) / rx, (-y1p - cyp) / ry) % (2 * math.pi)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi

    pts = []
    for k in range(1, steps + 1):
        th = theta1 + dtheta * (k / steps)
        pxp = rx * math.cos(th)
        pyp = ry * math.sin(th)
        pts.append((cos_phi * pxp - sin_phi * pyp + cx, sin_phi * pxp + cos_phi * pyp + cy))
    return pts


def parse_path(d, steps=18):
    """Converte um path SVG (M L H V C S A Z) em polilinhas [(pontos, fechado)]."""
    tokens = _TOKEN.findall(d)
    i, cmd = 0, None
    x = y = sx = sy = 0.0
    ctrl = None
    paths, current = [], []

    def num():
        nonlocal i
        value = float(tokens[i])
        i += 1
        return value

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
            if cmd in "Zz":
                if current:
                    paths.append((current, True))
                current, x, y, ctrl = [], sx, sy, None
                continue
        rel, op = cmd.islower(), cmd.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if op == "M":
            if len(current) > 1:
                paths.append((current, False))
            x, y = num() + ox, num() + oy
            sx, sy, current, ctrl = x, y, [(x, y)], None
            cmd = "l" if rel else "L"
        elif op == "L":
            x, y = num() + ox, num() + oy
            current.append((x, y))
            ctrl = None
        elif op == "H":
            x = num() + ox
            current.append((x, y))
            ctrl = None
        elif op == "V":
            y = num() + oy
            current.append((x, y))
            ctrl = None
        elif op in "CS":
            if op == "C":
                x1, y1 = num() + ox, num() + oy
            else:
                x1, y1 = (2 * x - ctrl[0], 2 * y - ctrl[1]) if ctrl else (x, y)
            x2, y2 = num() + ox, num() + oy
            ex, ey = num() + ox, num() + oy
            for k in range(1, steps + 1):
                t = k / steps
                u = 1 - t
                current.append((u**3 * x + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * ex,
                                u**3 * y + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * ey))
            x, y, ctrl = ex, ey, (x2, y2)
        elif op == "A":
            rx, ry, rot, la, sw = num(), num(), num(), num(), num()
            ex, ey = num() + ox, num() + oy
            for pt in arc_to_points(x, y, rx, ry, rot, la, sw, ex, ey, steps):
                current.append(pt)
            x, y, ctrl = ex, ey, None
        else:
            raise ValueError(f"Comando SVG sem suporte: {cmd}")
    if len(current) > 1:
        paths.append((current, False))
    return paths


def arc(cx, cy, r, start, end, steps=36):
    """Arco em graus (sentido horário, 0° = leste), como no PIL."""
    return [(cx + r * math.cos(math.radians(start + (end - start) * k / steps)),
             cy + r * math.sin(math.radians(start + (end - start) * k / steps)))
            for k in range(steps + 1)]


class Art:
    """Superfície RGBA em supersampling com coordenadas lógicas."""

    def __init__(self, size=None, origin=(0, 0), image=None):
        self.ox, self.oy = origin
        self.im = image if image is not None else Image.new(
            "RGBA", (round(size[0] * SS), round(size[1] * SS)), (0, 0, 0, 0))

    def px(self, x, y):
        return (x - self.ox) * SS, (y - self.oy) * SS

    def box(self, b):
        x1, y1 = self.px(b[0], b[1])
        x2, y2 = self.px(b[2], b[3])
        return round(x1), round(y1), round(x2), round(y2)

    def paste(self, layer, x, y, alpha=1.0):
        composite(self.im, with_alpha(layer, alpha) if alpha < 1 else layer, x, y)

    def shape(self, b, radius, fill=None, stops=None, horizontal=False,
              outline=None, width=1.0):
        x1, y1, x2, y2 = self.box(b)
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            return
        mask = rr_mask(w, h, radius * SS)
        if fill or stops:
            color = gradient((w, h), stops, horizontal) if stops else Image.new("RGBA", (w, h), fill)
            color.putalpha(ImageChops.multiply(color.getchannel("A"), mask))
            self.paste(color, x1, y1)
        if outline:
            layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(layer).rounded_rectangle(
                (0, 0, w - 1, h - 1), radius=max(0, min(radius * SS, w / 2, h / 2)),
                outline=outline, width=max(1, round(width * SS)))
            self.paste(layer, x1, y1)

    def shadow(self, b, radius, color, alpha, blur, spread=0, dx=0, dy=0, inset=False):
        """box-shadow do CSS (o externo não é desenhado sob o próprio elemento)."""
        x1, y1, x2, y2 = self.box(b)
        w, h = x2 - x1, y2 - y1
        sigma = blur * SS / 2
        element = rr_mask(w, h, radius * SS)
        if inset:
            hole = Image.new("L", (w, h), 0)
            s = spread * SS
            ImageDraw.Draw(hole).rounded_rectangle(
                (dx * SS + s, dy * SS + s, w - 1 + dx * SS - s, h - 1 + dy * SS - s),
                radius=max(0, radius - spread) * SS, fill=255)
            if sigma:
                hole = hole.filter(ImageFilter.GaussianBlur(sigma))
            a = ImageChops.multiply(element, ImageChops.invert(hole))
            layer = Image.new("RGBA", (w, h), tuple(color[:3]) + (0,))
            layer.putalpha(a.point(lambda v: round(v * alpha)))
            composite(self.im, layer, x1, y1)
            return
        m = round(3 * sigma + abs(spread) * SS + max(abs(dx), abs(dy)) * SS) + 2
        mask = Image.new("L", (w + 2 * m, h + 2 * m), 0)
        s = spread * SS
        ImageDraw.Draw(mask).rounded_rectangle(
            (m + dx * SS - s, m + dy * SS - s, m + w - 1 + dx * SS + s, m + h - 1 + dy * SS + s),
            radius=max(0, radius + spread) * SS, fill=255)
        if sigma:
            mask = mask.filter(ImageFilter.GaussianBlur(sigma))
        hole = Image.new("L", mask.size, 0)
        hole.paste(element, (m, m))
        a = ImageChops.multiply(mask, ImageChops.invert(hole)).point(lambda v: round(v * alpha))
        layer = Image.new("RGBA", mask.size, tuple(color[:3]) + (0,))
        layer.putalpha(a)
        composite(self.im, layer, x1 - m, y1 - m)

    def stroke(self, subpaths, color, width):
        """Traços com pontas e junções arredondadas, sem sobrepor alfa."""
        points = [self.px(x, y) for sp, _ in subpaths for x, y in sp]
        if not points:
            return
        wpx = width * SS
        pad = wpx + 2
        left = math.floor(min(p[0] for p in points) - pad)
        top = math.floor(min(p[1] for p in points) - pad)
        right = math.ceil(max(p[0] for p in points) + pad)
        bottom = math.ceil(max(p[1] for p in points) + pad)
        layer = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        r = wpx / 2
        for sp, closed in subpaths:
            local = [(px - left, py - top) for px, py in (self.px(x, y) for x, y in sp)]
            if closed:
                local.append(local[0])
            if len(local) > 1:
                draw.line(local, fill=color, width=max(1, round(wpx)), joint="curve")
            for qx, qy in (local[0], local[-1]):
                draw.ellipse((qx - r, qy - r, qx + r, qy + r), fill=color)
        self.paste(layer, left, top)


# --------------------------------------------------------------------------
# Ícones (viewBox 24 × 24, traços fiéis ao Google Stitch)
# --------------------------------------------------------------------------

def _moon():
    c1, r1, c2, r2 = (12.0, 12.0), 8.5, (16.5, 7.5), 7.0
    d = math.dist(c1, c2)
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    phi = math.degrees(math.atan2(c2[1] - c1[1], c2[0] - c1[0]))
    alpha = math.degrees(math.acos(a / r1))
    beta = math.degrees(math.acos((d - a) / r2))
    return [(arc(*c1, r1, phi + alpha, phi + 360 - alpha, 48), False),
            (arc(*c2, r2, phi + 180 - beta, phi + 180 + beta, 32), False)]


def _gear():
    points = []
    for k in range(8):
        base = k * 45
        for offset, radius in ((-15, 7.2), (-9, 9.6), (9, 9.6), (15, 7.2)):
            angle = math.radians(base + offset)
            points.append((12 + radius * math.cos(angle), 12 + radius * math.sin(angle)))
    return [(points, True), (arc(12, 12, 3, 0, 360, 32), True)]


ICONS = {
    "thermo": lambda: [([(14.5, 14.76), (14.5, 3.5)], False), (arc(12, 3.5, 2.5, 180, 360, 16), False),
                       ([(9.5, 3.5), (9.5, 14.76)], False), (arc(12, 18.5, 4.5, -56.25, 236.25, 40), False)],
    "power": lambda: [(arc(12, 12, 9, 315, 585, 48), False), ([(12, 3), (12, 12)], False)],
    "minus": lambda: [([(4, 12), (20, 12)], False)],
    "plus": lambda: [([(4, 12), (20, 12)], False), ([(12, 4), (12, 20)], False)],
    "mode": lambda: parse_path("M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"),
    "fan": lambda: parse_path(
        "M12 12c-2.5 0-4.5-2-4.5-4.5S9.5 3 12 3s4.5 2 4.5 4.5c0 .5-.1 1-.3 1.5"
        "M12 12c0 2.5 2 4.5 4.5 4.5S21 14.5 21 12s-2-4.5-4.5-4.5c-.5 0-1 .1-1.5.3"
        "M12 12c0-2.5-2-4.5-4.5-4.5S3 9.5 3 12s2 4.5 4.5 4.5c.5 0 1-.1 1.5-.3"
        "M12 12c2.5 0 4.5 2 4.5 4.5S14.5 21 12 21s-4.5-2-4.5-4.5c0-.5.1-1 .3-1.5"),
    "extras": _moon,
    "bedtime": _moon,
    "eco": lambda: parse_path("M5 19C5 19 6.5 10 14 7c0 0 1 7-4.5 10-2.5 1.5-4.5 2-4.5 2z"
                              "M5 19c3-3 7-5 14-7"),
    "gear": _gear,
    "settings": _gear,
    "plug": lambda: parse_path("M9 3v5h6V3M10 8v5a2 2 0 0 0 4 0V8M12 15v6"),
    "bolt": lambda: parse_path("M13 2L4 14h7l-2 8 11-12h-7l2-8z"),
    "airwave": lambda: parse_path("M3 8c3-3 6-3 9 0s6 3 9 0M3 12c3-3 6-3 9 0s6 3 9 0M3 16c3-3 6-3 9 0s6 3 9 0"),
    "volume_off": lambda: parse_path("M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"),
    "display": lambda: parse_path("M20 3H4c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h6l-2 3v1h8v-1l-2-3h6c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 13H4V5h16v11z"),
    "timer": lambda: parse_path("M12 3a9 9 0 1 0 9 9 9 9 0 0 0-9-9zm0 16a7 7 0 1 1 7-7 7 7 0 0 1-7 7zm.5-11H11v5l4.2 2.5.8-1.3-3.5-2.2z"),
    "meter": lambda: parse_path("M19 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm-7 13a4 4 0 1 1 4-4 4 4 0 0 1-4 4z"),
    "speed": lambda: parse_path("M12 4a9 9 0 0 0-9 9c0 2.8 1.3 5.3 3.3 6.9l1.4-1.4A7 7 0 1 1 19 13a6.9 6.9 0 0 1-2.7 5.5l1.4 1.4A8.9 8.9 0 0 0 21 13a9 9 0 0 0-9-9zm-1 5h2v4l3 3-1.4 1.4-3.6-3.4V9z"),
    "chevron_right": lambda: parse_path("M9 18l6-6-6-6"),
    "chevron_left": lambda: parse_path("M15 18l-6-6 6-6"),
    "arrow_back": lambda: parse_path("M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"),
    "check": lambda: parse_path("M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4L9 16.2z"),
    "sync": lambda: parse_path("M12 4V1L8 5l4 4V6a6 6 0 1 1-6 6H4a8 8 0 1 0 8-8z"),
    "wifi": lambda: parse_path("M1 9l2 2c4.97-4.97 13.03-4.97 18 0l2-2C16.93 2.93 7.08 2.93 1 9zm8 8l3 3 3-3c-1.65-1.66-4.34-1.66-6 0zm-4-4l2 2c2.76-2.76 7.24-2.76 10 0l2-2C15.14 9.14 8.87 9.14 5 13z"),
    "filter": lambda: parse_path("M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 14.93V17a1 1 0 0 1-2 0v-.07A8 8 0 0 1 4.07 11H4a1 1 0 0 1 0-2h.07A8 8 0 0 1 11 4.07V4a1 1 0 0 1 2 0v.07A8 8 0 0 1 19.93 11H20a1 1 0 0 1 0 2h-.07A8 8 0 0 1 13 16.93z"),
    "electrical_services": lambda: parse_path("M18 13c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zm0 8c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm-6-8V7h1V1h-2v6h-2V1H7v6h1v6c0 2.21 1.79 4 4 4v-2c-1.1 0-2-.9-2-2z"),
    "verified": lambda: parse_path("M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z"),
    "alarm_on": lambda: [([(12, 4), (12, 12), (16, 14)], False), (arc(12, 12, 8.5, 0, 360, 36), True)],
}


def icon(art, name, x, y, size, color, stroke):
    k = size / 24
    builder = ICONS.get(name)
    if not builder:
        return
    subpaths = [([(x + u * k, y + v * k) for u, v in pts], closed) for pts, closed in builder()]
    art.stroke(subpaths, color, stroke * k)


def render_icon(name, size, color, stroke=2.0, scale=1.0):
    """Gera uma imagem PIL RGBA transparente contendo o ícone vetorial."""
    art = Art((size, size))
    icon(art, name, 0, 0, size, color, stroke)
    final_size = (max(1, round(size * scale)), max(1, round(size * scale)))
    return art.im.resize(final_size, Image.Resampling.LANCZOS)


# --------------------------------------------------------------------------
# Componentes do Layout
# --------------------------------------------------------------------------

def background():
    """Fundo atmosférico #0E141B com degradê radial e 3 orbs bioluminescentes."""
    art = Art((WIDTH, HEIGHT))
    w, h = art.im.size
    rx, ry = 1.05 * WIDTH * SS, 0.85 * HEIGHT * SS
    cx, cy = WIDTH / 2 * SS, 160 * SS
    radial = Image.radial_gradient("L").resize((round(2 * rx), round(2 * ry)),
                                                Image.Resampling.BILINEAR)
    mask = Image.new("L", (w, h), 255)
    mask.paste(radial, (round(cx - rx), round(cy - ry)))
    art.im = Image.composite(Image.new("RGBA", (w, h), rgba("#090F16")),
                             Image.new("RGBA", (w, h), rgba("#0E141B")), mask)

    # Orb 1: Ciano primário (topo esquerdo) - animate-pulse glow
    glow1 = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(glow1).ellipse((-40, -40, 180, 180), fill=255)
    glow1 = glow1.filter(ImageFilter.GaussianBlur(55)).resize((w, h), Image.Resampling.BILINEAR)
    layer1 = Image.new("RGBA", (w, h), (0, 229, 255, 0))
    layer1.putalpha(glow1.point(lambda v: round(v * 0.12)))
    art.im.alpha_composite(layer1)

    # Orb 2: Azul secundário (topo direito)
    glow2 = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(glow2).ellipse((WIDTH - 140, 20, WIDTH + 80, 240), fill=255)
    glow2 = glow2.filter(ImageFilter.GaussianBlur(60)).resize((w, h), Image.Resampling.BILINEAR)
    layer2 = Image.new("RGBA", (w, h), (0, 166, 224, 0))
    layer2.putalpha(glow2.point(lambda v: round(v * 0.10)))
    art.im.alpha_composite(layer2)

    return art.im


def power_button(art, on):
    """Botão circular de Power com halo bioluminescente ciano quando ligado."""
    if on:
        art.shadow(POWER_BOX, 24, (0, 229, 255), 0.60, 24, spread=-2)
    art.shape(POWER_BOX, 24, fill=rgba("#1A2027", 0.9))
    if on:
        art.shape(POWER_BOX, 24, fill=rgba("#00E5FF", 0.12), outline=rgba("#00E5FF", 0.8), width=1.5)
        icon(art, "power", 330, 42, 24, rgba("#00E5FF"), 2.2)
    else:
        art.shape(POWER_BOX, 24, outline=rgba("#3B494C", 0.8), width=1.2)
        icon(art, "power", 330, 42, 24, rgba("#94A3B8"), 2.0)


def round_button(art, b, name):
    """Botão tátil circular [-] ou [+] com relevo suave."""
    art.shadow(b, 24, (0, 0, 0), 0.40, 14, spread=-2, dy=4)
    art.shape(b, 24, fill=rgba("#161C23", 0.85), outline=rgba("#3B494C", 0.6), width=1.0)
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    icon(art, name, cx - 11, cy - 11, 22, rgba("#DDE3ED"), 2.4)


def slider_track(art):
    """Trilha groove rebaixada do slider com sombra interna."""
    art.shape(TRACK_BOX, 14, fill=rgba("#090F16", 0.95))
    art.shadow(TRACK_BOX, 14, (0, 0, 0), 0.6, 5, dy=2, inset=True)
    art.shadow(TRACK_BOX, 14, (255, 255, 255), 0.06, 2, dy=-1, inset=True)
    art.shape(TRACK_BOX, 14, outline=rgba("#252A32", 0.8), width=1.0)


def slider_fill(art, temperature):
    """Pista ativa em gradiente ciano neon terminando no thumb circular brilhante."""
    knob = thumb_x(temperature)
    fill = (FILL_X, FILL_Y1, knob + 8, FILL_Y2)
    art.shadow(fill, 14, (0, 229, 255), 0.5, 12)
    art.shape(fill, 14, stops=[(0, rgba("#00A6E0")), (0.5, rgba("#00E5FF")),
                               (1, rgba("#C3F5FF"))], horizontal=True)
    thumb = (knob - 12, FILL_Y1 - 5, knob + 12, FILL_Y2 + 5)
    art.shadow(thumb, 12, (0, 229, 255), 0.95, 14)
    art.shape(thumb, 12, fill=rgba("#FFFFFF"), outline=rgba("#00E5FF"), width=2)
    art.shape((knob - 4.5, (FILL_Y1 + FILL_Y2) / 2 - 4.5, knob + 4.5, (FILL_Y1 + FILL_Y2) / 2 + 4.5),
              4.5, fill=rgba("#00E5FF"))


def plug_card_base(art):
    """Card integrado da Tomada EKAZA no Dashboard."""
    b = PLUG_CARD_BOX
    art.shadow(b, 18, (0, 0, 0), 0.35, 12, spread=-2, dy=4)
    art.shape(b, 18, fill=rgba("#161C23", 0.75), outline=rgba("#2F353D", 0.6), width=1.0)
    # Orb do ícone à esquerda
    orb_b = (b[0] + 12, b[1] + 8, b[0] + 48, b[1] + 44)
    art.shape(orb_b, 20, fill=rgba("#252A32", 0.9), outline=rgba("#3B494C", 0.4), width=1.0)
    icon(art, "plug", orb_b[0] + 8, orb_b[1] + 8, 20, rgba("#5BE9AD"), 2.0)
    # Botão pill "Medição ›" à direita
    pill_b = PLUG_ACTION_BOX
    art.shape(pill_b, 16, fill=rgba("#252A32", 0.8), outline=rgba("#00E5FF", 0.25), width=1.0)
    # O chevron é desenhado junto ao texto pelo Canvas, após medir a fonte real.


def card(art, index, active):
    """Cartão de vidro escuro; o ativo recebe borda e brilho neon ciano."""
    b = card_box(index)
    if active:
        art.shadow(b, 18, (0, 229, 255), 0.45, 14)
        art.shape(b, 18, stops=[(0, rgba("#004F58", 0.45)), (1, rgba("#161C23", 0.9))],
                  outline=rgba("#00E5FF", 0.9), width=2.0)
        icon(art, CARD_ICONS[index], b[0] + 14, b[1] + 14, 24, rgba("#00E5FF"), 2.2)
    else:
        art.shadow(b, 18, (0, 0, 0), 0.30, 10, spread=-2, dy=3)
        art.shape(b, 18, fill=rgba("#161C23", 0.75), outline=rgba("#2F353D", 0.5), width=1.0)
        art.shape((b[0] + 2, b[1] + 1, b[2] - 2, b[1] + 2), 1, fill=rgba("#FFFFFF", 0.05))
        icon(art, CARD_ICONS[index], b[0] + 14, b[1] + 14, 24, rgba("#BAC9CC"), 1.8)


def unit_layer():
    """Chassi split com acabamento 3D moderno, visor digital e aletas."""
    art = Art((TOP_BOX[2], TOP_BOX[3]))
    # Sombra do chassi
    art.shadow(UNIT_BOX, 18, (0, 0, 0), 0.70, 32, spread=-6, dy=14)
    art.shadow(UNIT_BOX, 18, (0, 0, 0), 0.35, 6, spread=-2, dy=3)
    # Corpo do chassi em degradê suave
    art.shape(UNIT_BOX, 18, stops=[(0, rgba("#2F353D")), (0.5, rgba("#252A32")),
                                   (1, rgba("#161C23"))], outline=rgba("#FFFFFF", 0.15), width=1.0)
    # Bevel superior sutil
    art.shape((UNIT_BOX[0] + 12, UNIT_BOX[1] + 2, UNIT_BOX[2] - 12, UNIT_BOX[1] + 4),
              1, fill=rgba("#FFFFFF", 0.20))
    # Dot e marca Elgin Inverter
    art.shape((UNIT_BOX[0] + 20, UNIT_BOX[1] + 32, UNIT_BOX[0] + 26, UNIT_BOX[1] + 38),
              3, fill=rgba("#00E5FF", 0.9))
    # Moldura do mini display digital
    art.shape(DISPLAY_BOX, 6, fill=rgba("#090F16", 0.85))
    art.shadow(DISPLAY_BOX, 6, (0, 0, 0), 0.25, 4, dy=1, inset=True)
    art.shape(DISPLAY_BOX, 6, outline=rgba("#3B494C", 0.7), width=1.0)
    # Flap inferior / aletas do ar
    art.shape((UNIT_BOX[0] + 8, UNIT_BOX[3] - 14, UNIT_BOX[2] - 8, UNIT_BOX[3] - 4),
              5, fill=rgba("#090F16", 0.95))
    # Aleta interna com linha luminosa ciano suave
    art.shape((UNIT_BOX[0] + 40, UNIT_BOX[3] - 10, UNIT_BOX[2] - 40, UNIT_BOX[3] - 8),
              1, fill=rgba("#00E5FF", 0.75))
    return art.im


WIND_PATHS = (
    ("M 40 0 C 80 40, 100 65, 160 65 C 220 65, 240 40, 280 0", 0.85, 2.5),
    ("M 70 0 C 100 35, 120 50, 160 50 C 200 50, 220 35, 250 0", 0.60, 1.8),
    ("M 110 0 C 130 25, 140 35, 160 35 C 180 35, 190 25, 210 0", 0.40, 1.2),
)


def wind_layer():
    """Feixes de ar com degradê ciano #00E5FF → transparente saindo sob o chassi."""
    w, h = 340, 125
    art = Art((w, h))
    for d, opacity, width in WIND_PATHS:
        pts = parse_path(d, 28)
        color = rgba("#00E5FF", opacity)
        art.stroke(pts, color, width)
    # Aplicar blur suave e gradiente vertical
    f_w, f_h = (WIND_BOX[2] - WIND_BOX[0]) * SS, (WIND_BOX[3] - WIND_BOX[1]) * SS
    mask_grad = gradient((f_w, f_h), [(0, rgba("#000000", 0.95)), (0.6, rgba("#000000", 0.6)),
                                      (1, rgba("#000000", 0.0))])
    resized = art.im.resize((f_w, f_h), Image.Resampling.LANCZOS)
    resized.putalpha(ImageChops.multiply(resized.getchannel("A"), mask_grad.getchannel("A")))
    return resized


def wind_frame(wind, t):
    """Quadro da animação de fluxo de vento contínuo."""
    scale = 1 + 0.06 * t
    opacity = 0.75 + 0.25 * t
    w, h = wind.size
    stretched = wind.resize((w, round(h * scale)), Image.Resampling.BILINEAR)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    composite(out, stretched, 0, (h - stretched.height) / 2 + 2 * t * SS)
    return with_alpha(out, opacity)


# --------------------------------------------------------------------------
# Montagem dos Assets
# --------------------------------------------------------------------------

def _crop(image, box):
    return image.crop(tuple(v * SS for v in box))


def render_assets(scale=1.0):
    """Gera as imagens de alta definição já reduzidas para a escala da janela."""

    def down(image, box):
        size = (max(1, round((box[2] - box[0]) * scale)), max(1, round((box[3] - box[1]) * scale)))
        return image.convert("RGB").resize(size, Image.Resampling.LANCZOS)

    def overlay(base, box, paint):
        art = Art(origin=box[:2], image=_crop(base, box))
        paint(art)
        return down(art.im, box)

    full = (0, 0, WIDTH, HEIGHT)
    bg = background()
    base = Art(image=bg.copy())

    # Elementos do Dashboard na imagem base
    icon(base, "thermo", 24, 34, 18, rgba("#00E5FF"), 2.2)
    round_button(base, MINUS_BOX, "minus")
    round_button(base, PLUS_BOX, "plus")
    slider_track(base)
    plug_card_base(base)

    for index in range(3):
        card(base, index, False)

    # Linha do rodapé e botões rápidos
    base.shape((24, FOOTER_LINE_Y, 366, FOOTER_LINE_Y + 1), 0, fill=rgba("#252A32", 0.6))
    round_button(base, (300, 786, 336, 822), "bolt")
    round_button(base, (342, 786, 378, 822), "gear")

    top = _crop(base.im, TOP_BOX)
    unit = unit_layer()
    wind = wind_layer()

    def top_frame(on, t=None):
        art = Art(image=top.copy())
        power_button(art, on)
        if t is not None:
            x, y, _, _ = art.box(WIND_BOX)
            art.paste(wind_frame(wind, t), x, y)
        art.im.alpha_composite(unit)
        return down(art.im, TOP_BOX)

    return {
        "blank": down(bg, full),
        "base": down(base.im, full),
        "top_off": top_frame(False),
        "top_on": [top_frame(True, i / (WIND_FRAMES - 1)) for i in range(WIND_FRAMES)],
        "eco": [overlay(base.im, ECO_BOX, lambda a, on=on: card(a, 3, on)) for on in (False, True)],
        "slider": [overlay(base.im, SLIDER_BOX, lambda a, t=t: slider_fill(a, t))
                   for t in range(MIN_TEMP, MAX_TEMP + 1)],
    }


if __name__ == "__main__":
    from pathlib import Path
    assets = render_assets(1.0)
    preview = assets["base"].copy()
    preview.paste(assets["top_on"][WIND_FRAMES // 2], TOP_BOX[:2])
    preview.paste(assets["eco"][1], ECO_BOX[:2])
    preview.paste(assets["slider"][8], SLIDER_BOX[:2])
    out = Path(__file__).with_name("preview_painel.png")
    preview.save(out)
    print("Salvo:", out)
