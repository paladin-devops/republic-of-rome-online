import pytest

from rorapp.actions.close_prosecutions import CloseProsecutionsAction
from rorapp.actions.close_senate import CloseSenateAction
from rorapp.actions.elect_governor import ElectGovernorAction
from rorapp.actions.vote_yea import VoteYeaAction
from rorapp.classes.faction_status_item import FactionStatusItem
from rorapp.classes.random_resolver import FakeRandomResolver
from rorapp.effects.meta.effect_executor import execute_effects_and_manage_actions
from rorapp.game_state.game_state_snapshot import GameStateSnapshot
from rorapp.helpers.end_prosecutions import end_prosecutions
from rorapp.helpers.governor_election import (
    format_governor_proposal,
    format_grouped_governor_proposal,
    governor_field_name,
)
from rorapp.helpers.kill_senator import kill_senator
from rorapp.models import Faction, Game, Log, Province, Senator


def _setup_all_factions_done(game: Game):
    for f in Faction.objects.filter(game=game):
        f.remove_status_item(FactionStatusItem.CALLED_TO_VOTE)
        f.add_status_item(FactionStatusItem.DONE)
        f.save()


@pytest.fixture
def governor_election_game(basic_game: Game):
    game = basic_game
    game.phase = Game.Phase.SENATE
    game.sub_phase = Game.SubPhase.GOVERNOR_ELECTION
    game.save()

    senators = list(Senator.objects.filter(game=game, alive=True))
    pm = senators[0]
    pm.add_title(Senator.Title.ROME_CONSUL)
    pm.add_title(Senator.Title.HRAO)
    pm.add_title(Senator.Title.PRESIDING_MAGISTRATE)
    pm.save()

    Province.objects.create(game=game, name="Sicilia", developed=False)
    return game


@pytest.mark.django_db
def test_end_prosecutions_enters_governor_election_when_forum_province_exists(
    prosecution_setup,
):
    # Arrange
    game, julius, cornelius, scipio = prosecution_setup
    Province.objects.create(game=game, name="Sicilia", developed=False)

    # Act
    end_prosecutions(game.id)

    # Assert
    game.refresh_from_db()
    assert game.sub_phase == Game.SubPhase.GOVERNOR_ELECTION


@pytest.mark.django_db
def test_skip_prosecution_enters_governor_election_when_forum_province_exists(
    prosecution_setup,
):
    # Arrange
    game, julius, cornelius, scipio = prosecution_setup
    Province.objects.create(game=game, name="Sicilia", developed=False)
    faction = Faction.objects.get(id=julius.faction_id)

    # Act
    result = CloseProsecutionsAction().execute(
        game.id, faction.id, {}, FakeRandomResolver()
    )

    # Assert
    assert result.success
    game.refresh_from_db()
    assert game.sub_phase == Game.SubPhase.GOVERNOR_ELECTION


@pytest.mark.django_db
def test_governor_elected_leaves_rome_and_assigns_term(
    governor_election_game: Game, resolver: FakeRandomResolver
):
    # Arrange
    game = governor_election_game
    senators = list(Senator.objects.filter(game=game, alive=True))
    pm = senators[0]
    candidate = senators[1]
    province = Province.objects.get(game=game, name="Sicilia")
    faction = Faction.objects.get(id=pm.faction_id)

    result = ElectGovernorAction().execute(
        game.id,
        faction.id,
        {"Province": province.id, "Governor": candidate.id},
        FakeRandomResolver(),
    )
    assert result.success

    game.refresh_from_db()
    game.votes_yea = 15
    game.votes_nay = 0
    game.save()
    _setup_all_factions_done(game)

    # Act
    execute_effects_and_manage_actions(game.id, resolver)

    # Assert
    province.refresh_from_db()
    candidate.refresh_from_db()
    assert province.governor_id == candidate.id
    assert province.term == 3
    assert province.elected_this_turn is True
    assert candidate.location == "Sicilia"
    assert province.governor_id is not None
    game.refresh_from_db()
    assert game.sub_phase == Game.SubPhase.OTHER_BUSINESS


@pytest.mark.django_db
def test_get_schema_excludes_defeated_governor_pairing_for_selected_province(
    governor_election_game: Game,
):
    # Arrange
    game = governor_election_game
    senators = list(Senator.objects.filter(game=game, alive=True))
    pm = senators[0]
    defeated_candidate = senators[1]
    alternate_candidate = senators[2]
    sicilia = Province.objects.get(game=game, name="Sicilia")
    macedonia = Province.objects.create(game=game, name="Macedonia", developed=True)
    faction = Faction.objects.get(id=pm.faction_id)

    game.defeated_proposals = [
        format_governor_proposal(sicilia.name, defeated_candidate)
    ]
    game.save()

    # Act
    actions = ElectGovernorAction().get_schema(GameStateSnapshot(game.id), faction.id)

    # Assert
    assert len(actions) == 1
    sicilia_governor_field = next(
        field
        for field in actions[0].field_descriptors
        if field["name"] == governor_field_name(sicilia.name)
    )
    macedonia_governor_field = next(
        field
        for field in actions[0].field_descriptors
        if field["name"] == governor_field_name(macedonia.name)
    )

    sicilia_option_ids = {option["id"] for option in sicilia_governor_field["options"]}
    macedonia_option_ids = {
        option["id"] for option in macedonia_governor_field["options"]
    }

    assert defeated_candidate.id not in sicilia_option_ids
    assert alternate_candidate.id in sicilia_option_ids
    assert defeated_candidate.id in macedonia_option_ids


@pytest.mark.django_db
def test_major_office_holder_ineligible_for_governor_election(
    governor_election_game: Game,
):
    # Arrange
    game = governor_election_game
    senators = list(Senator.objects.filter(game=game, alive=True))
    pm = senators[0]
    consul_candidate = senators[1]
    consul_candidate.add_title(Senator.Title.ROME_CONSUL)
    consul_candidate.save()
    province = Province.objects.get(game=game, name="Sicilia")
    faction = Faction.objects.get(id=pm.faction_id)

    # Act
    result = ElectGovernorAction().execute(
        game.id,
        faction.id,
        {"Province": province.id, "Governor": consul_candidate.id},
        FakeRandomResolver(),
    )

    # Assert
    assert not result.success
    assert "ineligible" in (result.message or "").lower()


@pytest.mark.django_db
def test_elected_governor_does_not_contribute_to_later_faction_vote(
    governor_election_game: Game, resolver: FakeRandomResolver
):
    # Arrange
    game = governor_election_game
    senators = list(Senator.objects.filter(game=game, alive=True))
    pm = senators[0]
    governor = senators[1]
    province = Province.objects.get(game=game, name="Sicilia")
    faction = Faction.objects.get(id=pm.faction_id)

    ElectGovernorAction().execute(
        game.id,
        faction.id,
        {"Province": province.id, "Governor": governor.id},
        FakeRandomResolver(),
    )
    game.refresh_from_db()
    game.votes_yea = 15
    game.votes_nay = 0
    game.save()
    _setup_all_factions_done(game)
    execute_effects_and_manage_actions(game.id, resolver)

    governor.refresh_from_db()
    assert governor.location == province.name

    game.current_proposal = "Deploy forces"
    game.votes_yea = 0
    game.votes_nay = 0
    game.save()
    for f in Faction.objects.filter(game=game):
        f.remove_status_item(FactionStatusItem.DONE)
        f.remove_status_item(FactionStatusItem.CALLED_TO_VOTE)
        f.save()
    faction.add_status_item(FactionStatusItem.CALLED_TO_VOTE)
    faction.save()
    in_rome_votes = sum(
        s.votes
        for s in faction.senators.filter(alive=True, location="Rome")
    )

    # Act
    result = VoteYeaAction().execute(game.id, faction.id, {}, FakeRandomResolver())

    # Assert
    assert result.success
    game.refresh_from_db()
    assert game.votes_yea == in_rome_votes
    governor.refresh_from_db()
    assert not governor.has_status_item(Senator.StatusItem.VOTED_YEA)


@pytest.mark.django_db
def test_auto_close_governor_elections_advances_when_no_eligible_candidates(
    governor_election_game: Game, resolver: FakeRandomResolver
):
    # Arrange
    game = governor_election_game
    game.current_proposal = None
    game.save()
    for senator in Senator.objects.filter(game=game, alive=True):
        senator.add_title(Senator.Title.ROME_CONSUL)
        senator.save()

    # Act
    execute_effects_and_manage_actions(game.id, resolver)

    # Assert
    game.refresh_from_db()
    assert game.sub_phase == Game.SubPhase.OTHER_BUSINESS
    log_texts = list(Log.objects.filter(game=game).values_list("text", flat=True))
    assert any(
        "no further governorship elections possible" in text.lower()
        for text in log_texts
    )


@pytest.mark.django_db
def test_governor_death_mid_senate_reopens_governor_election(
    governor_election_game: Game,
):
    # Arrange
    game = governor_election_game
    game.sub_phase = Game.SubPhase.OTHER_BUSINESS
    game.save()
    senators = list(Senator.objects.filter(game=game, alive=True))
    governor = senators[1]
    province = Province.objects.get(game=game, name="Sicilia")
    province.governor = governor
    province.term = 3
    province.elected_this_turn = True
    province.save()
    governor.location = province.name
    governor.save()

    # Act
    kill_senator(governor)

    # Assert
    province.refresh_from_db()
    game.refresh_from_db()
    assert province.governor_id is None
    assert province.term is None
    assert province.elected_this_turn is False
    assert game.sub_phase == Game.SubPhase.GOVERNOR_ELECTION


@pytest.mark.django_db
def test_grouped_governor_election_assigns_multiple_governors(
    governor_election_game: Game, resolver: FakeRandomResolver
):
    # Arrange
    game = governor_election_game
    senators = list(Senator.objects.filter(game=game, alive=True))
    pm = senators[0]
    sicilia_governor = senators[1]
    macedonia_governor = senators[2]
    sicilia = Province.objects.get(game=game, name="Sicilia")
    macedonia = Province.objects.create(game=game, name="Macedonia", developed=True)
    faction = Faction.objects.get(id=pm.faction_id)

    result = ElectGovernorAction().execute(
        game.id,
        faction.id,
        {
            "Provinces": [sicilia.id, macedonia.id],
            governor_field_name(sicilia.name): sicilia_governor.id,
            governor_field_name(macedonia.name): macedonia_governor.id,
        },
        FakeRandomResolver(),
    )
    assert result.success

    game.refresh_from_db()
    expected_proposal = format_grouped_governor_proposal(
        [(sicilia, sicilia_governor), (macedonia, macedonia_governor)]
    )
    assert game.current_proposal == expected_proposal

    game.votes_yea = 15
    game.votes_nay = 0
    game.save()
    _setup_all_factions_done(game)

    # Act
    execute_effects_and_manage_actions(game.id, resolver)

    # Assert
    game.refresh_from_db()
    sicilia.refresh_from_db()
    macedonia.refresh_from_db()
    sicilia_governor.refresh_from_db()
    macedonia_governor.refresh_from_db()
    assert sicilia.governor_id == sicilia_governor.id
    assert macedonia.governor_id == macedonia_governor.id
    assert sicilia_governor.location == "Sicilia"
    assert macedonia_governor.location == "Macedonia"
    assert game.sub_phase == Game.SubPhase.OTHER_BUSINESS


@pytest.mark.django_db
def test_grouped_governor_defeat_blocks_both_pairings_in_schema(
    governor_election_game: Game,
):
    # Arrange
    game = governor_election_game
    senators = list(Senator.objects.filter(game=game, alive=True))
    pm = senators[0]
    sicilia_candidate = senators[1]
    macedonia_candidate = senators[2]
    sicilia = Province.objects.get(game=game, name="Sicilia")
    macedonia = Province.objects.create(game=game, name="Macedonia", developed=True)
    faction = Faction.objects.get(id=pm.faction_id)

    game.defeated_proposals = [
        format_grouped_governor_proposal(
            [(sicilia, sicilia_candidate), (macedonia, macedonia_candidate)]
        )
    ]
    game.save()

    # Act
    actions = ElectGovernorAction().get_schema(GameStateSnapshot(game.id), faction.id)

    # Assert
    sicilia_governor_field = next(
        field
        for field in actions[0].field_descriptors
        if field["name"] == governor_field_name(sicilia.name)
    )
    macedonia_governor_field = next(
        field
        for field in actions[0].field_descriptors
        if field["name"] == governor_field_name(macedonia.name)
    )
    assert sicilia_candidate.id not in {
        option["id"] for option in sicilia_governor_field["options"]
    }
    assert macedonia_candidate.id not in {
        option["id"] for option in macedonia_governor_field["options"]
    }


@pytest.mark.django_db
def test_grouped_governor_election_rejects_duplicate_senator(
    governor_election_game: Game,
):
    # Arrange
    game = governor_election_game
    senators = list(Senator.objects.filter(game=game, alive=True))
    pm = senators[0]
    candidate = senators[1]
    sicilia = Province.objects.get(game=game, name="Sicilia")
    macedonia = Province.objects.create(game=game, name="Macedonia", developed=True)
    faction = Faction.objects.get(id=pm.faction_id)

    # Act
    result = ElectGovernorAction().execute(
        game.id,
        faction.id,
        {
            "Provinces": [sicilia.id, macedonia.id],
            governor_field_name(sicilia.name): candidate.id,
            governor_field_name(macedonia.name): candidate.id,
        },
        FakeRandomResolver(),
    )

    # Assert
    assert not result.success
    assert "multiple provinces" in (result.message or "").lower()


@pytest.mark.django_db
def test_close_senate_blocked_while_vacant_forum_province_has_eligible_candidates(
    governor_election_game: Game,
):
    # Arrange
    game = governor_election_game
    game.sub_phase = Game.SubPhase.OTHER_BUSINESS
    game.save()
    pm = Senator.objects.filter(game=game, alive=True).first()
    assert pm is not None and pm.faction_id is not None
    faction = Faction.objects.get(id=pm.faction_id)

    # Act
    result = CloseSenateAction().execute(game.id, faction.id, {}, FakeRandomResolver())

    # Assert
    assert not result.success
