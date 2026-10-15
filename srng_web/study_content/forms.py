import csv
from django import forms
from .models import Card, Tag

class CardCreationForm(forms.ModelForm):
    tag_names = forms.CharField(
        required=False,
        label='Tags',
        help_text='Separate tags with commas.',
    )

    class Meta:
        model = Card
        fields = (
            'question',
            'answer',
            'length',
            'grading_type',
            'grading_criteria',
            'llm_grading_info',
        )
        widgets = {
            'question': forms.Textarea(attrs={'rows': 4}),
            'answer': forms.Textarea(attrs={'rows': 6}),
            'grading_criteria': forms.Textarea(attrs={'rows': 4}),
            'llm_grading_info': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_tag_names(self):
        try:
            names = next(csv.reader(
                [self.cleaned_data['tag_names']],
                strict=True,
            ))
        except csv.Error:
            raise forms.ValidationError('Enter valid comma-separated tags.')

        names = list(dict.fromkeys(
            name.strip() for name in names if name.strip()
        ))
        max_length = Tag._meta.get_field('name').max_length
        if any(len(name) > max_length for name in names):
            raise forms.ValidationError(
                f'Each tag must be at most {max_length} characters.'
            )
        return names

    def save_tags(self):
        tags = [
            Tag.objects.get_or_create(name=name)[0]
            for name in self.cleaned_data['tag_names']
        ]
        self.instance.tags.set(tags)