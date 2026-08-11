from pathlib import Path

path = Path('omega/plugin.video.umbrella/resources/lib/debrid/deepbrid.py')
text = path.read_text(encoding='utf-8')

start = text.index('    def display_magnet_pack(\n')
end = text.index('    # -------------------------------------------------\n    # Usenet\n', start)
block = text[start:end]

assert block.count('    def display_magnet_pack(\n') == 1
assert block.count('    def add_uncached_torrent(\n') == 1

text = text[:start] + text[end:]
assert '    def display_magnet_pack(\n' not in text
assert '    def add_uncached_torrent(\n' not in text

path.write_text(text, encoding='utf-8')
