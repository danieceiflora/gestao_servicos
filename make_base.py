import re

with open('templates/base.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Match the layout part that we want to replace with {% block layout %}{% endblock %}
# It starts at <!-- Desktop Header --> and ends at {% endif %} after <!-- Mobile Bottom Navigation -->
start_str = '    <!-- Desktop Header -->'
end_str = '    </nav>\n    {% endif %}'

start_idx = text.find(start_str)
end_idx = text.find(end_str) + len(end_str)

if start_idx != -1 and end_idx != -1:
    new_text = text[:start_idx] + '    {% block layout %}{% endblock %}\n' + text[end_idx:]
    with open('templates/base_root.html', 'w', encoding='utf-8') as f:
        f.write(new_text)
    
    # Now let's extract that layout and put it in a new base.html
    layout_text = text[start_idx:end_idx]
    
    new_base = f"""{{% extends 'base_root.html' %}}
{{% load static %}}

{{% block layout %}}
{layout_text}
{{% endblock %}}
"""
    # Replace the messages repetition with the include using regex
    # find {% if messages %} ... {% endif %} and replace with {% include 'partials/messages.html' %}
    new_base_cleaned = re.sub(
        r'\{% if messages %\}.*?\{% endif %\}', 
        r'{% include "partials/messages.html" %}', 
        new_base, 
        flags=re.DOTALL
    )

    with open('templates/base.html', 'w', encoding='utf-8') as f:
        f.write(new_base_cleaned)

    print('base_root.html and base.html created/updated successfully.')
else:
    print('Patterns not found')

