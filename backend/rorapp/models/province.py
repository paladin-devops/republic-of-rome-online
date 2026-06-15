from django.db import models

from rorapp.models.game import Game
from rorapp.models.senator import Senator


class Province(models.Model):
    game = models.ForeignKey(
        Game, related_name="provinces", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=30)
    developed = models.BooleanField(default=False)
    term = models.PositiveSmallIntegerField(default=0)
    governor = models.ForeignKey(
        Senator,
        related_name="governorships",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
