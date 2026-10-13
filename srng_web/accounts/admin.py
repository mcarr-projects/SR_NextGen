from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User

@admin.register(User)
class CustomerUserAdmin(UserAdmin):
    model = User

    ordering = ('email',)
    list_display = (
        'email',
        'approval_status',
        'is_active',
        'is_staff',
    )
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
                ('Personal info', {'fields': ('first_name', 'last_name')}),
                ('SRNextGen', {'fields': ('approval_status',)}),
                (
                    'Permissions',
                    {
                        'fields': (
                            'is_active',
                            'is_staff',
                            'is_superuser',
                            'groups',
                            'user_permissions',
                        ),
                    },
                ),
                ('Important dates', {'fields': ('last_login', 'date_joined')}),
            )

    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': (
                    'email',
                    'password1',
                    'password2',
                    'approval_status',
                    'is_active',
                    'is_staff',
                ),
            },
        ),
    )

    search_fields = ('email',)