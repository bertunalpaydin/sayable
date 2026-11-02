from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.services import recogniser


class Command(BaseCommand):
    help = "Download and load the Whisper speech model so the first recording is quick."

    def handle(self, *args, **options):
        name = settings.SAYABLE["WHISPER_MODEL"]
        self.stdout.write(f"Preparing the speech model ({name}). The first time this downloads about 150 MB…")
        try:
            recogniser()._model()
        except Exception as err:
            raise CommandError(f"Could not prepare the speech model: {err}") from err
        self.stdout.write(self.style.SUCCESS("Speech model ready."))
