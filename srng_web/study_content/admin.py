from django.contrib import admin
from .models import Card, Tag

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    ordering = ('name',)

@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ('id', 'question', 'author', 'length', 'grading_type', 'is_deprecated')
    list_filter = ('length', 'grading_type', 'is_deprecated')
    search_fields = ('question', 'answer')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('tags',)