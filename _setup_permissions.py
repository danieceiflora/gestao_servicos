import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from services.models import ServiceOrder, ServiceOrderTask

def setup_groups():
    # 1. Colaboradores (Instaladores / Ajudantes)
    collab_group, _ = Group.objects.get_or_create(name='Colaboradores')
    
    # Permissões para Colaboradores: Ver Ordens e Ver Tarefas
    order_ct = ContentType.objects.get_for_model(ServiceOrder)
    task_ct = ContentType.objects.get_for_model(ServiceOrderTask)
    
    view_order = Permission.objects.get(codename='view_serviceorder', content_type=order_ct)
    view_task = Permission.objects.get(codename='view_serviceordertask', content_type=task_ct)
    change_task = Permission.objects.get(codename='change_serviceordertask', content_type=task_ct)
    
    collab_group.permissions.set([view_order, view_task, change_task])
    
    # 2. Gerentes
    manager_group, _ = Group.objects.get_or_create(name='Gerentes')
    # Gerentes podem fazer quase tudo nas ordens
    all_order_perms = Permission.objects.filter(content_type=order_ct)
    all_task_perms = Permission.objects.filter(content_type=task_ct)
    manager_group.permissions.set(list(all_order_perms) + list(all_task_perms))

    # 3. Administradores (Geralmente são superusers, mas criamos o grupo por segurança)
    admin_group, _ = Group.objects.get_or_create(name='Administradores')

    print("Grupos e permissões básicas configurados com sucesso!")

if __name__ == "__main__":
    setup_groups()
