import os

files = [
    'templates/services/equipe/task_list.html',
    'templates/services/equipe/task_detail.html'
]

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    content = content.replace('{% extends "base.html" %}', '{% extends "base_equipe.html" %}')
    content = content.replace("{% extends 'base.html' %}", '{% extends "base_equipe.html" %}')
    
    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)
print("done")
