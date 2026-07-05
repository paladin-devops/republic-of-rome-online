from typing import Any, Dict, List, Optional

from rorapp.actions.meta.action_base import ActionBase
from rorapp.actions.meta.execution_result import ExecutionResult
from rorapp.classes.faction_status_item import FactionStatusItem
from rorapp.classes.random_resolver import RandomResolver
from rorapp.game_state.game_state_live import GameStateLive
from rorapp.game_state.game_state_snapshot import GameStateSnapshot
from rorapp.helpers.governor_candidates import (
    get_eligible_governor_candidates,
    holds_major_office,
    vacant_forum_provinces,
)
from rorapp.helpers.governor_election import (
    format_grouped_governor_proposal,
    format_governor_proposal,
    governor_field_name,
    is_defeated_governor_pairing,
)
from rorapp.helpers.proposal_available import governor_election_proposal_available
from rorapp.helpers.senate_proposal import senate_open_for_proposals
from rorapp.models import AvailableAction, Faction, Game, Log, Province, Senator


class ElectGovernorAction(ActionBase):
    NAME = "Elect governor"
    POSITION = 0

    def is_allowed(
        self, game_state: GameStateLive | GameStateSnapshot, faction_id: int
    ) -> Optional[Faction]:
        faction = game_state.get_faction(faction_id)
        if (
            faction
            and senate_open_for_proposals(
                game_state, Game.SubPhase.GOVERNOR_ELECTION
            )
            and governor_election_proposal_available(game_state)
            and not any(
                s.has_status_item(Senator.StatusItem.UNANIMOUSLY_DEFEATED)
                for s in game_state.senators
            )
            and (
                any(
                    s
                    for s in game_state.senators
                    if s.faction
                    and s.faction.id == faction.id
                    and s.has_title(Senator.Title.PRESIDING_MAGISTRATE)
                )
                and not any(
                    f
                    for f in game_state.factions
                    if f.id != faction.id
                    and f.has_status_item(FactionStatusItem.PLAYED_TRIBUNE)
                )
                or faction.has_status_item(FactionStatusItem.PLAYED_TRIBUNE)
            )
        ):
            return faction
        return None

    def _eligible_provinces(
        self,
        vacant_provinces: List[Province],
        candidate_senators: List[Senator],
        defeated_proposals: list[str],
    ) -> List[Province]:
        eligible = []
        for province in vacant_provinces:
            if any(
                not is_defeated_governor_pairing(
                    province.name, senator, defeated_proposals
                )
                for senator in candidate_senators
            ):
                eligible.append(province)
        return eligible

    def _governor_options(
        self,
        province: Province,
        candidate_senators: List[Senator],
        defeated_proposals: list[str],
        *,
        use_province_signal: bool,
    ) -> List[dict]:
        options = []
        for senator in candidate_senators:
            if is_defeated_governor_pairing(
                province.name, senator, defeated_proposals
            ):
                continue
            option = {
                "value": senator.id,
                "object_class": "senator",
                "id": senator.id,
            }
            if use_province_signal:
                option["conditions"] = [
                    {
                        "value1": "signal:province_id",
                        "operation": "==",
                        "value2": province.id,
                    },
                ]
            options.append(option)
        return options

    def get_schema(
        self, game_state_snapshot: GameStateSnapshot, faction_id: int
    ) -> List[AvailableAction]:
        faction = self.is_allowed(game_state_snapshot, faction_id)
        if not faction:
            return []

        defeated_proposals = list(game_state_snapshot.game.defeated_proposals)
        vacant_provinces = vacant_forum_provinces(game_state_snapshot.game.id)
        candidate_senators = get_eligible_governor_candidates(
            game_state_snapshot.senators
        )
        eligible_provinces = self._eligible_provinces(
            vacant_provinces, candidate_senators, defeated_proposals
        )

        if not eligible_provinces:
            return []

        if len(eligible_provinces) == 1:
            province = eligible_provinces[0]
            governor_options = self._governor_options(
                province,
                candidate_senators,
                defeated_proposals,
                use_province_signal=True,
            )
            if not governor_options:
                return []
            return [
                AvailableAction.objects.create(
                    game=game_state_snapshot.game,
                    faction=faction,
                    base_name=self.NAME,
                    position=self.POSITION,
                    field_descriptors=[
                        {
                            "type": "select",
                            "name": "Province",
                            "options": [
                                {
                                    "value": province.id,
                                    "object_class": "province",
                                    "id": province.id,
                                    "signals": {
                                        "province_id": province.id,
                                    },
                                }
                            ],
                        },
                        {
                            "type": "select",
                            "name": "Governor",
                            "group_by": "faction",
                            "options": governor_options,
                        },
                    ],
                )
            ]

        province_options = [
            {
                "value": province.id,
                "object_class": "province",
                "id": province.id,
            }
            for province in eligible_provinces
        ]
        field_descriptors: List[dict] = [
            {
                "type": "multiselect",
                "name": "Provinces",
                "options": province_options,
            },
        ]
        for province in eligible_provinces:
            governor_options = self._governor_options(
                province,
                candidate_senators,
                defeated_proposals,
                use_province_signal=False,
            )
            if not governor_options:
                continue
            field_descriptors.append(
                {
                    "type": "select",
                    "name": governor_field_name(province.name),
                    "group_by": "faction",
                    "options": governor_options,
                }
            )

        return [
            AvailableAction.objects.create(
                game=game_state_snapshot.game,
                faction=faction,
                base_name=self.NAME,
                position=self.POSITION,
                field_descriptors=field_descriptors,
            )
        ]

    def _log_proposal(
        self,
        game_id: int,
        faction: Faction,
        faction_id: int,
        proposal: str,
        senators,
    ) -> None:
        if faction.has_status_item(FactionStatusItem.PLAYED_TRIBUNE):
            faction.remove_status_item(FactionStatusItem.PLAYED_TRIBUNE)
            faction.add_status_item(FactionStatusItem.PROPOSED_VIA_TRIBUNE)
            Log.create_object(
                game_id,
                f"{faction.display_name} used their tribune to propose the motion: {proposal}.",
            )
        else:
            presiding_magistrate = next(
                (
                    s
                    for s in senators
                    if s.faction is not None
                    and s.faction.id == faction_id
                    and s.has_title(Senator.Title.PRESIDING_MAGISTRATE)
                ),
                None,
            )
            pm_name = (
                presiding_magistrate.display_name
                if presiding_magistrate
                else "Presiding Magistrate"
            )
            Log.create_object(
                game_id,
                f"{pm_name} proposed the motion: {proposal}.",
            )
        faction.save()

    def _validate_pairing(
        self,
        game: Game,
        province: Province,
        senator: Senator,
    ) -> Optional[str]:
        if senator.location != "Rome":
            return f"{senator.display_name} is not in Rome."
        if holds_major_office(senator):
            return f"{senator.display_name} holds a major office and is ineligible."
        if is_defeated_governor_pairing(
            province.name, senator, game.defeated_proposals
        ):
            return "This proposal was previously rejected."
        return None

    def execute(
        self,
        game_id: int,
        faction_id: int,
        selection: Dict[str, Any],
        random_resolver: RandomResolver,
    ) -> ExecutionResult:
        game = Game.objects.get(id=game_id)
        faction = Faction.objects.get(game=game_id, id=faction_id)
        senators = list(Senator.objects.filter(game_id=game_id, alive=True))
        vacant_count = Province.objects.filter(
            game_id=game_id, governor__isnull=True
        ).count()

        if vacant_count >= 2 and "Provinces" in selection:
            try:
                province_ids = [int(pid) for pid in selection["Provinces"]]
            except (TypeError, ValueError):
                return ExecutionResult(False, "Invalid province selection.")

            if not province_ids:
                return ExecutionResult(False, "Select at least one province.")

            pairings: list[tuple[Province, Senator]] = []
            used_senator_ids: set[int] = set()

            for province_id in sorted(set(province_ids)):
                try:
                    province = Province.objects.get(
                        game_id=game_id, id=province_id, governor__isnull=True
                    )
                except Province.DoesNotExist:
                    return ExecutionResult(False, "Invalid province selection.")

                try:
                    senator_id = int(selection[governor_field_name(province.name)])
                    senator = next(s for s in senators if s.id == senator_id)
                except (KeyError, TypeError, ValueError, StopIteration):
                    return ExecutionResult(
                        False,
                        f"Select a governor for {province.name}.",
                    )

                if senator_id in used_senator_ids:
                    return ExecutionResult(
                        False,
                        f"{senator.display_name} cannot govern multiple provinces.",
                    )

                error = self._validate_pairing(game, province, senator)
                if error:
                    return ExecutionResult(False, error)

                used_senator_ids.add(senator_id)
                pairings.append((province, senator))

            current_proposal = format_grouped_governor_proposal(pairings)
            if game.has_defeated_proposal(current_proposal):
                return ExecutionResult(False, "This proposal was previously rejected.")

            game.current_proposal = current_proposal
            game.save()

            for _, senator in pairings:
                senator.add_status_item(Senator.StatusItem.NAMED_IN_PROPOSAL)
                senator.save()

            self._log_proposal(
                game_id, faction, faction_id, current_proposal, senators
            )
            return ExecutionResult(True)

        try:
            province = Province.objects.get(
                game_id=game_id, id=selection["Province"], governor__isnull=True
            )
            senator = next(s for s in senators if s.id == selection["Governor"])
        except (Province.DoesNotExist, KeyError, TypeError, StopIteration):
            return ExecutionResult(False, "Invalid province or governor selection.")

        error = self._validate_pairing(game, province, senator)
        if error:
            return ExecutionResult(False, error)

        current_proposal = format_governor_proposal(province.name, senator)
        if game.has_defeated_proposal(current_proposal):
            return ExecutionResult(False, "This proposal was previously rejected.")

        game.current_proposal = current_proposal
        game.save()

        senator.add_status_item(Senator.StatusItem.NAMED_IN_PROPOSAL)
        senator.save()

        self._log_proposal(game_id, faction, faction_id, current_proposal, senators)
        return ExecutionResult(True)