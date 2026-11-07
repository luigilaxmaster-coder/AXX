import re

def update_html(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. raw.finish includes
    content = content.replace(
        "['obsidian', 'prism', 'smoke'].includes(raw.finish",
        "['obsidian', 'prism', 'smoke', 'opticalglass'].includes(raw.finish"
    )

    # 2. p.finish includes
    content = content.replace(
        "['obsidian', 'prism', 'smoke'].includes(p.finish",
        "['obsidian', 'prism', 'smoke', 'opticalglass'].includes(p.finish"
    )

    # 3. x.finish includes
    content = content.replace(
        "['obsidian', 'prism', 'smoke'].includes(x.finish",
        "['obsidian', 'prism', 'smoke', 'opticalglass'].includes(x.finish"
    )

    # 4. Finish cards button
    target_btn = '<button data-finish="smoke"><i class="finish-smoke"></i><strong>Smoke Chrome</strong><span>Reflejo difuso; acabado ahumado.</span></button>'
    new_btn = target_btn + '<button data-finish="opticalglass"><i class="finish-prism"></i><strong>Optical Glass</strong><span>Volumen cromático y cristal óptico.</span></button>'
    if 'data-finish="opticalglass"' not in content:
        content = content.replace(target_btn, new_btn)

    # 5. Script tag
    if 'scripts/optical-glass.js' not in content:
        content = content.replace(
            '<script src="scripts/transfer.js"></script>',
            '<script src="scripts/transfer.js"></script><script src="scripts/optical-glass.js"></script>'
        )

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated {path} successfully!")

if __name__ == '__main__':
    update_html('1.AXX/Axx.html')
