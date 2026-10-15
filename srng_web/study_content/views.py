from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView
from .forms import CardCreationForm
from .models import Card, Tag

class CardCreateView(LoginRequiredMixin, CreateView):
    form_class = CardCreationForm
    template_name = 'study_content/add_card.html'
    success_url = reverse_lazy('study_content:add_card')

    def form_valid(self,form):
        form.instance.author = self.request.user

        with transaction.atomic():
            response = super().form_valid(form)
            form.save_tags()

        messages.success(self.request, 'Card Created')
        return response

class CardBrowseView(LoginRequiredMixin, ListView):
    model = Card
    template_name = 'study_content/card_browser.html'
    context_object_name = 'cards'

    def get_queryset(self):
        cards = Card.objects.prefetch_related('tags').order_by('id')

        for name in self.request.GET.getlist('tag'):
            cards = cards.filter(tags__name=name)

        return cards.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tags'] = Tag.objects.order_by('name')
        context['selected_tags'] = self.request.GET.getlist('tag')
        return context