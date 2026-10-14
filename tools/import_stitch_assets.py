"""Extrai SVGs do HTML Stitch como dados; nunca executa o HTML fornecido."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parent.parent


class SvgCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons, self.styles, self.current = [], [], None

    def handle_starttag(self, tag, attrs):
        if tag == 'svg':
            self.current = []
            self.current_style = {key: value for key, value in attrs
                                  if key in ('stroke-linecap', 'stroke-linejoin')}
        elif self.current is not None and tag in ('path', 'line', 'circle', 'polyline', 'polygon', 'rect'):
            values = dict(attrs)
            allowed = {'d', 'x1', 'y1', 'x2', 'y2', 'cx', 'cy', 'r', 'points', 'x', 'y', 'rx', 'width', 'height'}
            self.current.append((tag, {key: val for key, val in values.items() if key in allowed}))

    def handle_endtag(self, tag):
        if tag == 'svg' and self.current is not None:
            self.icons.append(self.current)
            self.styles.append(self.current_style)
            self.current = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip', type=Path)
    args = parser.parse_args()
    with zipfile.ZipFile(args.zip) as archive:
        html = archive.read('code.html').decode('utf-8')
    collector = SvgCollector()
    collector.feed(html)
    # Ordem dos SVGs do flyout no code.html fornecido pelo usuário.
    mapping = {'power': (0, 2.2), 'mode': (1, 1.8), 'chevron': (2, 2.5),
               'fan': (3, 1.8), 'eco': (4, 2), 'plug': (6, 1.8),
               'display': (8, 1.8), 'extras': (9, 1.8), 'temperature': (11, 1.8),
               'temperature_options': (12, 2), 'connected': (14, 2), 'settings': (15, 1.8),
               'tray': (20, 2.5)}
    output = ROOT/'assets'/'stitch'/'icons'
    output.mkdir(parents=True, exist_ok=True)
    for name, (index, stroke) in mapping.items():
        shapes = collector.icons[index]
        tags = ['<' + tag + ' ' + ' '.join(f'{key}="{value}"' for key, value in attrs.items()) + '/>'
                for tag, attrs in shapes]
        caps = ''.join(f' {key}="{value}"' for key, value in collector.styles[index].items())
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
               f'stroke="#ffffff" stroke-width="{stroke}"{caps}>\n'
               + '\n'.join(tags) + '\n</svg>\n')
        (output/f'{name}.svg').write_text(svg, encoding='utf-8')
    # Apenas controles adicionais da aplicação que não existem no flyout Stitch.
    complements = {
        'sleep': '<path d="M21 12.8A9 9 0 1 1 11.2 3A7 7 0 0 0 21 12.8Z"/>',
        'refresh': '<path d="M20 7A9 9 0 1 0 21 14M20 3v5h-5"/>',
    }
    for name, shapes in complements.items():
        (output/f'{name}.svg').write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            'stroke="#ffffff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">\n'
            + shapes + '\n</svg>\n', encoding='utf-8')
    fonts = re.search(r"fluent:\s*\[([^\]]+)\]", html).group(1)
    manifest = {'source': 'code.html do ZIP Stitch fornecido pelo usuário',
                'font_stack': re.findall(r"'([^']+)'", fonts),
                'original_icons': sorted(mapping), 'complementary_icons': sorted(complements),
                'raster_size': 192, 'raster_note': 'PNG transparente de alta resolução derivado do SVG; Pillow adapta à escala Tk.'}
    (output.parent/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'{len(mapping)} ícones originais e {len(complements)} complementos extraídos.')


if __name__ == '__main__':
    main()
