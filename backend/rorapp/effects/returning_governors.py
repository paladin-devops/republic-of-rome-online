from rorapp.classes.faction_status_item import FactionStatusItem
from rorapp.classes.random_resolver import RandomResolver
from rorapp.effects.meta.effect_base import EffectBase
from rorapp.game_state.game_state_snapshot import GameStateSnapshot
from rorapp.models import Game, Log, Province, Senator


class ReturningGovernorsEffect(EffectBase):

    def validate(self, game_state: GameStateSnapshot) -> bool:
        if not (
            game_state.game.phase == Game.Phase.REVENUE
            and game_state.game.sub_phase == Game.SubPhase.REDISTRIBUTION
            and all(f.has_status_item(FactionStatusItem.DONE) for f in game_state.factions)
        ):
            return False

        # Only consider this effect if there is actual work (a non-rebel
        # governor whose province still needs its term reduced / return).
        return Province.objects.filter(
            game=game_state.game.id,
            governor__isnull=False,
            governor__rebel=False,
        ).exists()

    def execute(self, game_id: int, random_resolver: RandomResolver) -> bool:
        from rorapp.helpers.returning_governors import return_governors

        # The actual logic lives in the helper so it can be called exactly
        # once from RedistributionDoneEffect.
        return_governors(game_id)
        return True
