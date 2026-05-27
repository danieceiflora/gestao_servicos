from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.db.models import Q
from .models import Product, StockMovement, User
from .forms import ProductForm, StockMovementForm

def is_manager(user):
    return user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]

class ManagerRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_manager(self.request.user)

class ProductListView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'services/product_list.html'
    context_object_name = 'products'
    paginate_by = 20

    def get_queryset(self):
        queryset = Product.objects.all()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(code__icontains=search)
            )
        return queryset

class ProductCreateView(LoginRequiredMixin, ManagerRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'services/product_form.html'
    success_url = reverse_lazy('product_list')

    def form_valid(self, form):
        messages.success(self.request, "Produto cadastrado com sucesso.")
        return super().form_valid(form)

class ProductUpdateView(LoginRequiredMixin, ManagerRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'services/product_form.html'
    success_url = reverse_lazy('product_list')

    def form_valid(self, form):
        messages.success(self.request, "Produto atualizado com sucesso.")
        return super().form_valid(form)

class StockMovementCreateView(LoginRequiredMixin, ManagerRequiredMixin, CreateView):
    model = StockMovement
    form_class = StockMovementForm
    template_name = 'services/stock_movement_form.html'
    success_url = reverse_lazy('product_list')

    def form_valid(self, form):
        movement = form.save(commit=False)
        movement.user = self.request.user
        
        product = movement.product
        if movement.movement_type == StockMovement.MovementType.IN:
            product.current_stock += movement.quantity
        else:
            product.current_stock -= movement.quantity
        
        product.save()
        movement.save()
        
        messages.success(self.request, f"Movimentação de {movement.get_movement_type_display()} realizada com sucesso.")
        return redirect(self.success_url)

@login_required
def product_stock_history(request, pk):
    product = get_object_or_404(Product, pk=pk)
    movements = product.movements.all().select_related('user', 'service_order')
    
    context = {
        'product': product,
        'movements': movements,
    }
    return render(request, 'services/product_stock_history.html', context)
