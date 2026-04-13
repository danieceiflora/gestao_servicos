import os, glob, re

for f in glob.glob('templates/**/*.html', recursive=True) + glob.glob('services/**/*.py', recursive=True):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    if 'id.hex' in content or '|slice:":8"' in content:
        new_content = re.sub(r'id\.hex\[:8\]', 'number', content)
        new_content = re.sub(r'id\.hex\|slice:":8"', 'number', new_content)
        if new_content != content:
            with open(f, 'w', encoding='utf-8') as file:
                file.write(new_content)
            print(f"Updated {f}")