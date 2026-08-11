from pathlib import Path

path = Path('omega/plugin.video.umbrella/resources/lib/debrid/deepbrid.py')
text = path.read_text(encoding='utf-8-sig')
start_marker = '    def resolve_usenet(\n'
end_marker = '    def add_usenet_url_dialog(self):\n'
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0 or end <= start:
    raise SystemExit('resolve_usenet block markers not found')
if text.count(start_marker) != 1:
    raise SystemExit('resolve_usenet marker is not unique')
text = text[:start] + text[end:]
if '    def resolve_usenet(\n' in text:
    raise SystemExit('resolve_usenet still present after patch')
path.write_text(text, encoding='utf-8')
