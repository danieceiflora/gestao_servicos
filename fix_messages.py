import re

with open('templates/base.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Let's cleanly replace the messed up messages block
start_str = '{% include "partials/messages.html" %}'
end_str = '{% block content %}'

start_idx = text.find(start_str)
end_idx = text.find(end_str)

if start_idx != -1 and end_idx != -1:
    new_text = text[:start_idx] + '{% include "partials/messages.html" %}\n\n        ' + text[end_idx:]
    with open('templates/base.html', 'w', encoding='utf-8') as f:
        f.write(new_text)
    print('fixed')
else:
    print('Pattern not found')
