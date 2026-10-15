from django.urls import path
from .views import CardCreateView, CardBrowseView

app_name = 'study_content'

urlpatterns = [
    path('cards/add_card/', CardCreateView.as_view(), name='add_card'),
    path('cards/card_browser/', CardBrowseView.as_view(), name='card_browse'),
]