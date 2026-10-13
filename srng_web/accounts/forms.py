from django.contrib.auth.forms import UserCreationForm

from .models import User

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('email',)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = False
        user.approval_status = User.ApprovalStatus

        if commit:
            user.save()

        return user