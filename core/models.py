from django.conf import settings
from django.db import models


class UserSettings(models.Model):
    SENSITIVITY_CHOICES = [
        ("low", "Only the most likely problems"),
        ("normal", "Balanced"),
        ("high", "Flag anything that might be a problem"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="sayable_settings")
    sensitivity = models.CharField(max_length=10, choices=SENSITIVITY_CHOICES, default="normal")
    use_claude = models.BooleanField(default=False)
    claude_api_key = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"Settings for {self.user}"


class Script(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scripts")
    title = models.CharField(max_length=120)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class Attempt(models.Model):
    """One recording: a profile sentence or a piece of a script."""

    PROFILE, REHEARSAL = "profile", "rehearsal"
    KIND_CHOICES = [(PROFILE, "Profile sentence"), (REHEARSAL, "Rehearsal")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    sentence_key = models.CharField(max_length=10, blank=True)
    script = models.ForeignKey(Script, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="attempts")
    expected_text = models.TextField()
    heard_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} by {self.user} at {self.created_at:%Y-%m-%d %H:%M}"


class WordResult(models.Model):
    """How one expected word came out. The audio itself is never stored."""

    STATUS_CHOICES = [("ok", "Heard"), ("unclear", "Unclear"),
                      ("misheard", "Misheard"), ("missed", "Missed")]

    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="words")
    position = models.PositiveIntegerField()
    expected = models.CharField(max_length=64)
    heard = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    confidence = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["attempt", "position"]

    def __str__(self):
        return f"{self.expected} ({self.status})"
