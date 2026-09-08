from django.db import models


class DemoState(models.Model):
    """Which layout the demo storefront is currently serving.

    A single row. Flipping it is what "breaking the source" means: the same
    products, marked up a different way, exactly as a real redesign would
    arrive -- without warning and without changing the facts.
    """

    class Layout(models.TextChoices):
        ORIGINAL = "v1", "Original markup"
        REDESIGNED = "v2", "Full redesign -- rows stop matching entirely"
        SUBTLE = "v3", "Silent break -- rows still match, two fields do not"

    layout = models.CharField(max_length=4, choices=Layout.choices, default=Layout.ORIGINAL)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls) -> "DemoState":
        state, _ = cls.objects.get_or_create(pk=1)
        return state

    def __str__(self) -> str:
        return f"demo layout {self.layout}"
