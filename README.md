# prcvlabs.org

The source for [prcvlabs.org](https://prcvlabs.org), Perceive's project history.

- `index.md` is the page text. Edit this.
- `template.html` is the page shell (styles, contents sidebar, lightbox script).
- `build.py` turns the two into `index.html`, which GitHub Pages serves as-is.
- `images/` and `media/` hold the figures and demo videos.

After editing `index.md`, rebuild and commit the result:

```
python3 build.py
git add index.md index.html
git commit -m "..."
git push
```

The builder needs only Python 3. The Markdown conventions it understands (front
matter, section headings with `{#id .class}` attributes, figures with a caption
line, `[redacted]`) are described at the top of `build.py`.
