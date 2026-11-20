from django.contrib import admin

from .models import Article, ArticleStep, Category, ContextLink


class ArticleContentInline(admin.StackedInline):
    """Os filhos são parte do artigo, com a mesma permissão editorial."""
    extra = 0

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm('ajuda.view_article') or request.user.has_perm('ajuda.change_article')

    def has_add_permission(self, request, obj=None):
        return request.user.has_perm('ajuda.change_article' if obj else 'ajuda.add_article')

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm('ajuda.change_article')

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm('ajuda.change_article')


class ArticleStepInline(ArticleContentInline):
    model = ArticleStep
    fields = ('sort_order', 'title', 'content', 'screenshot', 'image', 'image_alt')
    readonly_fields = ('screenshot',)


class ContextLinkInline(ArticleContentInline):
    model = ContextLink


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'module', 'sort_order')
    list_filter = ('module',)
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'status', 'audience', 'featured', 'reviewed_at', 'updated_at')
    list_filter = ('status', 'category', 'audience', 'featured')
    search_fields = ('title', 'summary', 'content')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at', 'source_key', 'source_hash')
    list_select_related = ('category',)
    inlines = [ArticleStepInline, ContextLinkInline]
    fieldsets = (
        (None, {'fields': ('title', 'slug', 'category', 'summary')}),
        ('Publicação e público', {'fields': ('status', 'audience', 'featured', 'sort_order', 'reviewed_at')}),
        ('Instruções (texto simples)', {'fields': ('objective', 'prerequisites', 'content', 'expected_result', 'warnings')}),
        ('Vídeo', {'fields': ('video_url',)}),
        ('Controle de atualização', {'fields': ('created_at', 'updated_at', 'source_key', 'source_hash'), 'classes': ('collapse',)}),
    )
