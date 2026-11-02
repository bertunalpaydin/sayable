from django.contrib import admin

from .models import Attempt, Script, UserSettings, WordResult


class WordResultInline(admin.TabularInline):
    model = WordResult
    extra = 0


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "created_at")
    list_filter = ("kind",)
    inlines = [WordResultInline]


@admin.register(Script)
class ScriptAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "updated_at")


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "sensitivity", "use_claude")
    exclude = ("claude_api_key",)
