import xml.etree.ElementTree as ET

tree = ET.parse("backend/data/ttml/828491e7-ad83-4152-957c-1e9bffa61671.ttml")
ns = {"tt": "http://www.w3.org/ns/ttml"}
lines = []
for p in tree.findall(".//tt:p", ns):
    text = p.attrib.get("data-text", "")
    lines.append(text)

lyrics_text = "\n".join(lines)
with open("scratch_lyrics.txt", "w") as f:
    f.write(lyrics_text)
