"""Assets exatos do Stitch e famílias nativas da pilha de fontes fornecida."""
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageColor, ImageTk

ICON_DIR = Path(__file__).resolve().parent.parent/'assets'/'stitch'/'icons'


def font_family(available, size, weight='normal'):
    """Mapeia a família Variable do HTML às faces óticas que o Tk enumera."""
    names = set(available)
    if weight == 'mono':
        return 'Consolas' if 'Consolas' in names else 'Courier New'
    role = 'Small' if size <= 12 else 'Display' if size >= 20 else 'Text'
    variable = f'Segoe UI Variable {role}'
    if weight == 'semibold':
        # GDI/Tk pode truncar o nome da face a 31 caracteres.
        matches = sorted(name for name in names if name.startswith(variable+' Semib'))
        if matches:
            return matches[0]
    for candidate in (variable, 'Segoe UI Variable', 'Segoe UI'):
        if candidate in names:
            if weight == 'semibold' and candidate+' Semibold' in names:
                return candidate+' Semibold'
            return candidate
    return 'Arial' if 'Arial' in names else 'TkDefaultFont'


@lru_cache(maxsize=32)
def icon_alpha(name):
    with Image.open(ICON_DIR/f'{name}.png') as image:
        return image.convert('RGBA').getchannel('A')


def icon_image(name, color, pixels):
    alpha = icon_alpha(name).resize((pixels, pixels), Image.Resampling.LANCZOS)
    image = Image.new('RGBA', (pixels, pixels), ImageColor.getrgb(color)+(255,))
    image.putalpha(alpha)
    return image


def draw_stitch_icon(app, name, x, y, color, size):
    """Mantém PhotoImages vivos e ajusta o raster uma única vez para a escala."""
    root = getattr(app, 'root', None)
    if root is None:
        return None  # testes de comportamento usam Canvas simulado
    pixels = max(1, round(size*getattr(app, 'scale', 1.0)))
    rotation = 180 if name == 'back' else 0
    source = 'chevron' if name == 'back' else name
    key = (source, color, pixels, rotation)
    cache = app.__dict__.setdefault('icon_images', {})
    if key not in cache:
        image = icon_image(source, color, pixels)
        if rotation:
            image = image.rotate(rotation)
        cache[key] = ImageTk.PhotoImage(image, master=root)
    return app.canvas.create_image(x, y, image=cache[key], anchor='nw')
