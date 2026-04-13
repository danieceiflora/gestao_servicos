import re
with open('templates/services/home.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix paragraph
new_p = '''        {% if user.is_manager %}
        <p class="text-sm text-slate-500">Aqui está um resumo das atividades da sua equipe hoje.</p>
        {% endif %}'''

text = text.replace('<p class="text-sm text-slate-500">Aqui está um resumo das atividades da sua equipe hoje.</p>', new_p)

# We want to re-order the layout based on `if not user.is_manager` vs `else`
# Let's extract the two blocks.
stats_start = text.find('    <!-- Quick Stats -->')
actions_start = text.find('    <!-- Actions Section -->')
# Find the end of Actions Section (it ends with {% endif %}</div>)
# Actually, let's just find the chunks.
actions_end = text.rfind('</div>', actions_start) # Last </div> of the space-y-6

stats_block = text[stats_start:actions_start].strip()
actions_block = text[actions_start:actions_end].strip()

# Now reconstruct
if stats_start != -1 and actions_start != -1:
    new_html = text[:stats_start].strip() + '\n\n'
    
    new_html += '    {% if not user.is_manager %}\n'
    new_html += '    ' + actions_block.replace('\n', '\n    ') + '\n\n'
    new_html += '    ' + stats_block.replace('\n', '\n    ') + '\n'
    new_html += '    {% else %}\n'
    new_html += '    ' + stats_block.replace('\n', '\n    ') + '\n\n'
    new_html += '    ' + actions_block.replace('\n', '\n    ') + '\n'
    new_html += '    {% endif %}\n\n</div>\n{% endblock %}'
    
    with open('templates/services/home.html', 'w', encoding='utf-8') as f:
        f.write(new_html)
    print("done")
else:
    print("could not find sections")
