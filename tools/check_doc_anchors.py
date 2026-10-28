import re
import sys
from pathlib import Path

def main():
    with open(Path(__file__).resolve().parents[1] / 'app' / 'resources' / 'index.html', 'r', encoding='utf-8') as f:
        text = f.read()

    hrefs = set(re.findall(r'href="#([^"]+)"', text))
    ids = set(re.findall(r'id="([^"]+)"', text))

    dead = hrefs - ids
    print('Dead anchors:', dead)

if __name__ == '__main__':
    main()
