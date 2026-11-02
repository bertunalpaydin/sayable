from django import forms

from .models import Script, UserSettings


class ScriptForm(forms.ModelForm):
    class Meta:
        model = Script
        fields = ["title", "text"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Interview answers, team update, conference talk…"}),
            "text": forms.Textarea(attrs={"rows": 14, "placeholder": "Paste or write what you are going to say."}),
        }


class SettingsForm(forms.ModelForm):
    claude_api_key = forms.CharField(
        required=False,
        label="Claude API key",
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}),
        help_text="Leave empty to keep the key you saved before.",
    )
    remove_key = forms.BooleanField(required=False, label="Remove my saved key")

    class Meta:
        model = UserSettings
        fields = ["sensitivity", "use_claude", "claude_api_key"]
        widgets = {"sensitivity": forms.RadioSelect}
        labels = {
            "sensitivity": "How many words to flag",
            "use_claude": "Ask Claude for alternatives that fit the sentence",
        }

    def save(self, commit=True):
        prefs = super().save(commit=False)
        if self.cleaned_data.get("remove_key"):
            prefs.claude_api_key = ""
        elif not self.cleaned_data.get("claude_api_key"):
            prefs.claude_api_key = self.initial.get("claude_api_key", "")
        if commit:
            prefs.save()
        return prefs
