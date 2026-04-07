import sys
fn = r"c:\Users\danie\OneDrive\Área de Trabalho\gestao_servicos\templates\services\orders\calendar.html"
with open(fn, 'r', encoding='utf-8') as f:
    text = f.read()
text = text.replace("if (endDateStr) {", "console.log('DATAs RECEBIDAS no modal:', dateStr, endDateStr);\n        if (endDateStr) {")
with open(fn, 'w', encoding='utf-8') as f:
    f.write(text)
