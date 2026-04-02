"""
Script de debug para testar o formset de equipe
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from services.forms import ServiceOrderTeamFormSet

# Criar formset vazio (como na view task_add)
formset = ServiceOrderTeamFormSet()

print("=== DEBUG FORMSET ===")
print(f"Total forms: {formset.total_form_count()}")
print(f"Extra forms: {formset.extra}")
print(f"Initial forms: {formset.initial_form_count()}")
print("\n=== PRIMEIRO FORM ===")
if formset.forms:
    first_form = formset.forms[0]
    print(f"Professional field: {first_form['professional']}")
    print(f"Professional queryset count: {first_form.fields['professional'].queryset.count()}")
    print(f"Role field: {first_form['role']}")
    print(f"Role queryset count: {first_form.fields['role'].queryset.count()}")
else:
    print("Nenhum form no formset!")

print("\n=== MANAGEMENT FORM ===")
print(formset.management_form)
