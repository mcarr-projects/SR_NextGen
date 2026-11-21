from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Card


class CardCreationTests(TestCase):
    def test_anonymous_visitor_is_redirected_to_login(self):
        url = reverse("study_content:add_card")
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_signed_in_user_can_save_a_card(self):
        author = get_user_model().objects.create(email="author@example.com")
        self.client.force_login(author)
        url = reverse("study_content:add_card")
        response = self.client.post(url, {
            "question": "What is the capital of Japan?",
            "answer": "Tokyo",
            "length": "short",
            "grading_type": "binary",
        })

        self.assertRedirects(response, url)
        card = Card.objects.get()
        self.assertEqual(card.author, author)
        self.assertEqual(card.question, "What is the capital of Japan?")
        self.assertEqual(card.answer, "Tokyo")
