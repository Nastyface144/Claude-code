"""Генератор фирменных ассетов канала NVX / CODE.

Собирает SVG-исходники в brand/svg и рендерит PNG в brand/png.
Запуск:  python3 brand/build.py   (нужен cairosvg: pip install cairosvg)
"""
import pathlib
import cairosvg

ROOT = pathlib.Path(__file__).parent
SVG_DIR = ROOT / "svg"
PNG_DIR = ROOT / "png"

# --- фирменная палитра -------------------------------------------------
VIOLET_HI = "#9B6BFF"   # светлый акцент / центр свечения
VIOLET = "#6D3BE8"      # основной
VIOLET_DEEP = "#2A1467"  # глубокая тень градиента
INK = "#07080B"          # фон обложек
SMOKE = "#8A8FA0"        # вторичный текст
WHITE = "#FFFFFF"

SANS = "DejaVu Sans"
MONO = "DejaVu Sans Mono"

GLOW = f"""
  <defs>
    <radialGradient id="glow" cx="50%" cy="40%" r="72%">
      <stop offset="0%"  stop-color="{VIOLET_HI}"/>
      <stop offset="52%" stop-color="{VIOLET}"/>
      <stop offset="100%" stop-color="{VIOLET_DEEP}"/>
    </radialGradient>
  </defs>
"""


def avatar(glyph_svg: str) -> str:
    """Квадрат 512x512: заливка градиентом + тонкое кольцо + глиф по центру."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  {GLOW}
  <rect width="512" height="512" fill="url(#glow)"/>
  <circle cx="256" cy="256" r="243" fill="none" stroke="#FFFFFF" stroke-opacity="0.22" stroke-width="6"/>
{glyph_svg}
</svg>"""


# A — приглашение командной строки  >_
AVATAR_A = avatar(f"""  <g transform="translate(-18,0)" stroke="{WHITE}" stroke-width="34"
     stroke-linecap="round" stroke-linejoin="round" fill="none">
    <polyline points="192,188 258,254 192,320"/>
    <line x1="292" y1="322" x2="356" y2="322"/>
  </g>""")

# B — знак ветки git: ствол, ответвление и три узла
AVATAR_B = avatar(f"""  <g stroke="{WHITE}" stroke-width="24" stroke-linecap="round" fill="none">
    <path d="M198 214 V300"/>
    <path d="M198 258 C262 258, 314 254, 314 214"/>
  </g>
  <g fill="{WHITE}">
    <circle cx="198" cy="180" r="32"/>
    <circle cx="198" cy="334" r="32"/>
    <circle cx="314" cy="180" r="32"/>
  </g>""")

# C — текстовый логотип NVX
AVATAR_C = avatar(f"""  <text x="256" y="256" fill="{WHITE}" font-family="{SANS}" font-size="118"
        font-weight="bold" letter-spacing="4" text-anchor="middle" dominant-baseline="central">NVX</text>""")


def cover_base(extra_defs: str = "") -> str:
    """Общая подложка сторис 1080x1920: чернильный фон, сетка, фиолетовое свечение."""
    return f"""  <defs>
    <radialGradient id="halo" cx="50%" cy="0%" r="80%">
      <stop offset="0%" stop-color="{VIOLET}" stop-opacity="0.42"/>
      <stop offset="100%" stop-color="{VIOLET}" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
      <path d="M60 0 H0 V60" fill="none" stroke="#FFFFFF" stroke-opacity="0.045" stroke-width="1"/>
    </pattern>{extra_defs}
  </defs>
  <rect width="1080" height="1920" fill="{INK}"/>
  <rect width="1080" height="1920" fill="url(#grid)"/>
  <rect width="1080" height="1920" fill="url(#halo)"/>"""


def plaque(x=72, y=112) -> str:
    """Плашка канала в углу — ставится на каждую историю, это и есть узнаваемость."""
    return f"""  <g>
    <rect x="{x}" y="{y}" width="272" height="58" rx="29" fill="#FFFFFF" fill-opacity="0.08"
          stroke="#FFFFFF" stroke-opacity="0.16" stroke-width="1.5"/>
    <g transform="translate({x + 26},{y + 29}) scale(0.62)" stroke="{WHITE}" stroke-width="6"
       stroke-linecap="round" stroke-linejoin="round" fill="none">
      <polyline points="-16,-14 -2,0 -16,14"/>
      <line x1="4" y1="14" x2="20" y2="14"/>
    </g>
    <text x="{x + 76}" y="{y + 38}" fill="{WHITE}" font-family="{MONO}" font-size="26"
          font-weight="bold" letter-spacing="3">NVX / CODE</text>
  </g>"""


def footer(y=1768) -> str:
    return f"""  <line x1="72" y1="{y}" x2="1008" y2="{y}" stroke="#FFFFFF" stroke-opacity="0.12" stroke-width="2"/>
  <text x="72" y="{y + 52}" fill="{SMOKE}" font-family="{MONO}" font-size="30" letter-spacing="2">t.me/nvx_code</text>
  <text x="1008" y="{y + 52}" fill="{VIOLET_HI}" font-family="{MONO}" font-size="30"
        letter-spacing="2" text-anchor="end">#code</text>"""


# Обложка 1 — крупный заголовок.
# Вся типографика держится в колонке 72..1008 и в безопасной зоне сторис
# (сверху ~220 px занимает шапка Telegram, снизу ~320 px — панель ответа).
COVER_HEADLINE = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" viewBox="0 0 1080 1920">
{cover_base()}
{plaque()}
  <text x="72" y="700"  fill="{WHITE}" font-family="{SANS}" font-size="118" font-weight="bold">ЗАГОЛОВОК</text>
  <text x="72" y="838"  fill="{WHITE}" font-family="{SANS}" font-size="118" font-weight="bold">В ДВЕ</text>
  <text x="72" y="976"  fill="{VIOLET_HI}" font-family="{SANS}" font-size="118" font-weight="bold">СТРОКИ</text>
  <rect x="72" y="1028" width="180" height="10" rx="5" fill="{VIOLET_HI}"/>
  <text x="72" y="1126" fill="{SMOKE}" font-family="{SANS}" font-size="40">Подзаголовок — одна мысль, не больше</text>
{footer(1660)}
</svg>"""

# Обложка 2 — карточка с кодом
CODE_LINES = [
    ("$ ", "git commit -m \"ship it\"", VIOLET_HI),
    ("", "[main 4f2a1c] ship it", SMOKE),
    ("", " 3 files changed, 128 (+)", SMOKE),
    ("$ ", "npm run deploy", VIOLET_HI),
    ("", "build ok  ->  prod", "#5BE39A"),
]
code_svg = ""
for i, (prefix, text, color) in enumerate(CODE_LINES):
    ty = 916 + i * 62
    code_svg += (f'    <text x="150" y="{ty}" font-family="{MONO}" font-size="34">'
                 f'<tspan fill="{VIOLET_HI}">{prefix}</tspan>'
                 f'<tspan fill="{color}">{text}</tspan></text>\n')

COVER_CODE = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" viewBox="0 0 1080 1920">
{cover_base()}
{plaque()}
  <text x="72" y="640" fill="{WHITE}" font-family="{SANS}" font-size="92" font-weight="bold">ЧТО Я СЕГОДНЯ</text>
  <text x="72" y="742" fill="{VIOLET_HI}" font-family="{SANS}" font-size="92" font-weight="bold">СДЕЛАЛ</text>
  <g>
    <rect x="108" y="790" width="864" height="430" rx="28" fill="#0E1016"
          stroke="#FFFFFF" stroke-opacity="0.14" stroke-width="2"/>
    <circle cx="152" cy="838" r="9" fill="#FF5F57"/>
    <circle cx="182" cy="838" r="9" fill="#FEBC2E"/>
    <circle cx="212" cy="838" r="9" fill="#28C840"/>
{code_svg}  </g>
  <text x="72" y="1320" fill="{SMOKE}" font-family="{SANS}" font-size="40">Короткий комментарий к коду</text>
{footer(1660)}
</svg>"""

ASSETS = {
    "avatar-a-prompt": (AVATAR_A, 512, 512),
    "avatar-b-branch": (AVATAR_B, 512, 512),
    "avatar-c-wordmark": (AVATAR_C, 512, 512),
    "cover-headline": (COVER_HEADLINE, 1080, 1920),
    "cover-code": (COVER_CODE, 1080, 1920),
}

if __name__ == "__main__":
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    for name, (markup, w, h) in ASSETS.items():
        (SVG_DIR / f"{name}.svg").write_text(markup, encoding="utf-8")
        cairosvg.svg2png(bytestring=markup.encode("utf-8"),
                         write_to=str(PNG_DIR / f"{name}.png"),
                         output_width=w, output_height=h)
        print(f"ok  {name}  {w}x{h}")
