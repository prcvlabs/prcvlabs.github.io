#!/usr/bin/env python3
"""Build index.html from index.md and template.html.

usage: python3 build.py          (paths are relative to this file)

index.md is Markdown with a few conventions:

  ---                      front matter at the top: title, brand, years, byline
                           (byline parts separated by " · ")
  Paragraphs before the first "##" heading form the abstract; a leading
  **Abstract.** becomes its label.
  ## Heading {#id .class toc="Label" num="0."}
                           starts a section. The default class, "report", is
                           numbered with roman numerals and listed in the
                           contents with its ### sub-headings. Other classes
                           (funding, precursor) are listed as plain links,
                           using toc="..." as the link text.
  ---                      a line of dashes in the body closes the open section
  ### Sub-heading          gets an id and a contents entry
  ![](images/figNN.webp)   a figure; the line after it is the caption, and a
  Figure 3: *caption*      leading "Figure N:" or "Demo:" becomes its label
  ![](media/name.mp4) {.hero}
                           a looping video (media/name.webm, name.mp4 and
                           name-poster.webp); .hero makes it the page hero
  - item   /   1. item     lists
  Blocks that start with an HTML tag are copied through untouched.
  Inline: *em*, **strong**, ***strong em***, [text](url), inline HTML, and
  [redacted] for a name that is withheld. Emphasis does not nest beyond ***.
"""
import html
import os
import re

here = os.path.dirname(os.path.abspath(__file__))
REDACTED = '<span class="redacted" role="img" aria-label="name redacted">██████</span>'
ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']


# ---------- inline markdown ----------
INLINE = re.compile(
    r'\[redacted\]'
    r'|\[([^\]]+)\]\(([^)\s]+)\)'            # [text](url)
    r'|\*\*\*([^*\s](?:[^*]*?[^*\s])?)\*\*\*'   # ***strong em***
    r'|\*\*([^*\s](?:[^*]*?[^*\s])?)\*\*'       # **strong**
    r'|\*([^*\s](?:[^*]*?[^*\s])?)\*'           # *em*
    r'|<[^>]+>')                             # inline html, copied through


def esc(text):
    """Escape & (unless it already starts an entity); < > stay for inline html."""
    return re.sub(r'&(?!#?\w+;)', '&amp;', text)


def inline(md):
    out, pos = [], 0
    for m in INLINE.finditer(md):
        out.append(esc(md[pos:m.start()]))
        pos = m.end()
        if m.group(0) == '[redacted]':
            out.append(REDACTED)
        elif m.group(1) is not None:
            out.append(f'<a href="{m.group(2)}">{inline(m.group(1))}</a>')
        elif m.group(3) is not None:
            out.append(f'<strong><em>{inline(m.group(3))}</em></strong>')
        elif m.group(4) is not None:
            out.append(f'<strong>{inline(m.group(4))}</strong>')
        elif m.group(5) is not None:
            out.append(f'<em>{inline(m.group(5))}</em>')
        else:
            out.append(m.group(0))
    out.append(esc(md[pos:]))
    return ''.join(out)


def plain(md):
    """Markdown -> plain text (for alt text and contents entries)."""
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', md)
    t = re.sub(r'<[^>]+>', '', t)
    return t.replace('*', '')


def slug(t):
    return re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')[:60]


def split_attrs(line):
    """'Heading {#id .cls key="v"}' -> ('Heading', {...})"""
    m = re.search(r'\s*\{([^}]*)\}\s*$', line)
    attrs = {'class': []}
    if not m:
        return line, attrs
    for tok in re.findall(r'#[\w-]+|\.[\w-]+|[\w-]+="[^"]*"', m.group(1)):
        if tok[0] == '#':
            attrs['id'] = tok[1:]
        elif tok[0] == '.':
            attrs['class'].append(tok[1:])
        else:
            k, v = tok.split('=', 1)
            attrs[k] = v.strip('"')
    return line[:m.start()], attrs


def webp_size(path):
    with open(path, 'rb') as f:
        d = f.read(30)
    assert d[:4] == b'RIFF' and d[8:12] == b'WEBP', path
    chunk = d[12:16]
    if chunk == b'VP8X':
        return (1 + int.from_bytes(d[24:27], 'little'),
                1 + int.from_bytes(d[27:30], 'little'))
    if chunk == b'VP8 ':
        return (int.from_bytes(d[26:28], 'little') & 0x3fff,
                int.from_bytes(d[28:30], 'little') & 0x3fff)
    if chunk == b'VP8L':
        b = int.from_bytes(d[21:25], 'little')
        return (b & 0x3fff) + 1, ((b >> 14) & 0x3fff) + 1
    raise ValueError(f'unknown webp chunk {chunk!r} in {path}')


# ---------- document ----------
class Builder:
    def __init__(self):
        self.out = []
        self.abstract = []
        self.toc_pre = []        # [(label, id)]
        self.toc = []            # [(text, id, [(text, id)])]
        self.used_ids = set()
        self.section = None      # (cls, id, indent)
        self.in_abstract = False
        self.n_reports = 0

    def uid(self, base):
        i, b = 2, base
        while b in self.used_ids:
            b = f'{base}-{i}'
            i += 1
        self.used_ids.add(b)
        return b

    @property
    def indent(self):
        if self.section:
            return self.section[2] + ('  ' if self.section[2] else '')
        return '    ' if self.in_abstract else '    '

    def emit(self, s):
        (self.abstract if self.in_abstract else self.out).append(self.indent + s)

    def close(self):
        if self.in_abstract:
            self.abstract.append('    </div>')
            self.in_abstract = False
        if self.section:
            self.out.append(self.section[2] + '</section>')
            self.section = None

    def heading2(self, line):
        text, a = split_attrs(line)
        self.close()
        cls = a['class'][0] if a['class'] else 'report'
        if a.get('id'):
            sid = a['id']
            self.used_ids.add(sid)
        else:
            sid = self.uid(slug(plain(text)))
        ind = '' if cls == 'report' else '    '
        self.section = (cls, sid, ind)
        self.out.append(f'{ind}<section class="{cls}" id="{sid}" aria-labelledby="{sid}-h">')
        if cls == 'report':
            self.n_reports += 1
            self.toc.append((text, sid, []))
            self.emit(f'<h2 class="report-date" id="{sid}-h"><span class="eyebrow">Report</span>'
                      f'<span class="num">{ROMAN[self.n_reports]}.</span>{inline(text)}</h2>')
        else:
            self.toc_pre.append((a.get('toc', plain(text)), sid))
            num = f'<span class="num">{a["num"]}</span>' if a.get('num') else ''
            self.emit(f'<h2 id="{sid}-h">{num}{inline(text)}</h2>')

    def heading3(self, line):
        text, _ = split_attrs(line)
        prefix = self.section[1] + '-' if self.section else ''
        hid = self.uid(prefix + slug(plain(text)))
        if self.section and self.section[0] == 'report':
            self.toc[-1][2].append((text, hid))
        self.emit(f'<h3 id="{hid}">{inline(text)}</h3>')

    def figure(self, line, caption):
        m = re.match(r'!\[([^\]]*)\]\(([^)]+)\)(.*)$', line)
        alt_md, src, rest = m.group(1), m.group(2), m.group(3)
        _, a = split_attrs(rest)
        cap = ''
        label = re.match(r'(Figure \d+|Demo):\s*(.*)$', caption, re.S)
        if label:
            cap = f'<span class="fig-label">{label.group(1)}</span> {inline(label.group(2))}'
        elif caption:
            cap = inline(caption)
        figcap = f'\n<figcaption>{cap}</figcaption>' if cap else ''
        if src.endswith('.mp4'):
            name = re.sub(r'^media/|\.mp4$', '', src)
            cls = 'demo hero' if 'hero' in a['class'] else 'demo'
            self.emit(f'<figure class="{cls}"><video autoplay loop muted playsinline '
                      f'preload="metadata" poster="media/{name}-poster.webp">'
                      f'<source src="media/{name}.webm" type="video/webm">'
                      f'<source src="media/{name}.mp4" type="video/mp4"></video>'
                      f'{figcap}\n</figure>')
            return
        w, h = webp_size(os.path.join(here, src))
        alt = alt_md or re.sub(r'^(Figure \d+|Demo)[.:]\s*', '', plain(caption))[:240]
        alt = html.escape(alt, quote=True)
        self.emit(f'<figure><a class="zoom" href="{src}" aria-label="Enlarge figure">'
                  f'<img src="{src}" alt="{alt}" width="{w}" height="{h}" loading="lazy" '
                  f'decoding="async"></a>{figcap}\n</figure>')

    def list(self, lines):
        ordered = bool(re.match(r'\d+\.', lines[0]))
        items, start = [], None
        for ln in lines:
            m = re.match(r'(?:-|(\d+)\.)\s+(.*)$', ln)
            if m:
                if ordered and start is None:
                    start = int(m.group(1))
                items.append(m.group(2))
            else:
                items[-1] += ' ' + ln.strip()
        tag = 'ol' if ordered else 'ul'
        st = f' start="{start}"' if ordered and start != 1 else ''
        self.emit(f'<{tag}{st}>\n' + '\n'.join(f'<li>{inline(i)}</li>' for i in items) + f'\n</{tag}>')

    def paragraph(self, text):
        if not self.section:
            if not self.in_abstract:
                self.abstract.append('    <div class="abstract">')
                self.in_abstract = True
            m = re.match(r'\*\*([^*]+)\*\*\s*(.*)$', text, re.S)
            if m:
                self.emit(f'<p><span class="label">{esc(m.group(1))}</span>{inline(m.group(2))}</p>')
                return
        self.emit(f'<p>{inline(text)}</p>')

    def run(self, body):
        lines = body.split('\n')
        i, n = 0, len(lines)
        while i < n:
            ln = lines[i]
            if not ln.strip():
                i += 1
                continue
            if ln.startswith('## '):
                self.heading2(ln[3:].strip()); i += 1
            elif ln.startswith('### '):
                self.heading3(ln[4:].strip()); i += 1
            elif re.match(r'-{3,}\s*$', ln):
                self.close(); i += 1
            elif ln.startswith('!['):
                cap = []
                i += 1
                while i < n and lines[i].strip():
                    cap.append(lines[i].strip()); i += 1
                self.figure(ln.strip(), ' '.join(cap))
            elif re.match(r'(?:-|\d+\.)\s', ln):
                block = []
                while i < n and lines[i].strip():
                    block.append(lines[i]); i += 1
                self.list(block)
            elif re.match(r'<[a-zA-Z/!]', ln):
                block = []
                while i < n and lines[i].strip():
                    block.append(lines[i]); i += 1
                self.out.append('\n'.join(block))
            else:
                block = []
                while i < n and lines[i].strip() and not lines[i].startswith(('## ', '### ', '![')):
                    block.append(lines[i].strip()); i += 1
                self.paragraph(' '.join(block))
        self.close()

    def toc_html(self):
        pre = ''.join(f'<a class="toc-pre" href="#{sid}">{esc(label)}</a>' for label, sid in self.toc_pre)
        li = []
        for text, sid, subs in self.toc:
            sub = ''.join(
                f'<li><a href="#{h}">{inline(re.sub(r"^[0-9]+[.]\s*", "", t).split(":")[0].rstrip("."))}</a></li>'
                for t, h in subs)
            li.append(f'<li><a href="#{sid}">{inline(text)}</a>' + (f'<ol>{sub}</ol>' if sub else '') + '</li>')
        return pre + '<ol>' + ''.join(li) + '</ol>'


def main():
    src = open(os.path.join(here, 'index.md'), encoding='utf-8').read()
    meta = {}
    m = re.match(r'---\n(.*?)\n---\n', src, re.S)
    if m:
        for ln in m.group(1).split('\n'):
            if ':' in ln:
                k, v = ln.split(':', 1)
                meta[k.strip()] = v.strip()
        src = src[m.end():]
    b = Builder()
    b.run(src)
    byline = '<span class="sep">·</span>'.join(html.escape(p) for p in meta.get('byline', '').split(' · '))
    tpl = open(os.path.join(here, 'template.html'), encoding='utf-8').read()
    page = (tpl.replace('{{TITLE}}', html.escape(meta.get('title', '')))
               .replace('{{BRAND}}', html.escape(meta.get('brand', '')))
               .replace('{{BYLINE}}', byline)
               .replace('{{YEARS}}', html.escape(meta.get('years', '')))
               .replace('{{ABSTRACT}}', '\n'.join(b.abstract))
               .replace('{{TOC}}', b.toc_html())
               .replace('{{CONTENT}}', '\n'.join(b.out)))
    open(os.path.join(here, 'index.html'), 'w', encoding='utf-8').write(page)
    print(f'index.html: {len(b.toc)} reports, {sum(len(s[2]) for s in b.toc)} sub-headings, '
          f'{len(b.toc_pre)} front sections')


if __name__ == '__main__':
    main()
