import pytest
from rorapp.classes.faction_status_item import FactionStatusItem
from rorapp.effects.meta.effect_executor import execute_effects_and_manage_actions
from rorapp.models import Faction, Game, Legion, Province, Senator


def _setup_for_returning(game: Game, term: int = 1, corrupt: bool = False, num_garrisons: int = 0):
    """Put game at end of revenue (redistribution complete) and attach governor(s)."""
    game.phase = Game.Phase.REVENUE
    game.sub_phase = Game.SubPhase.REDISTRIBUTION
    game.save()

    # Mark all factions done so redistribution_done will trigger after our effect
    for faction in Faction.objects.filter(game=game):
        faction.add_status_item(FactionStatusItem.DONE)
        faction.save()

    # Pick a senator to be governor (from first faction)
    gov_senator = Senator.objects.filter(game=game, faction__isnull=False, alive=True).first()
    assert gov_senator is not None

    province = Province.objects.create(
        game=game,
        name="Sicilia",
        developed=False,
        term=term,
        governor=gov_senator,
    )
    gov_senator.location = "Sicilia"
    if corrupt:
        gov_senator.corrupt = True
    gov_senator.save()

    for i in range(num_garrisons):
        # Use high numbers unlikely to collide with existing 1-4; tests may create more
        Legion.objects.create(game=game, number=20 + i, veteran=False, province=province)

    return gov_senator, province


@pytest.mark.django_db
def test_governor_term_reduced_but_does_not_return_when_term_was_2(basic_game: Game):
    # Arrange
    gov, prov = _setup_for_returning(basic_game, term=2)

    # Act
    execute_effects_and_manage_actions(basic_game.id)

    # Assert
    prov.refresh_from_db()
    gov.refresh_from_db()
    assert prov.term == 1
    assert prov.governor_id == gov.id
    assert gov.location == "Sicilia"
    # game should have advanced past revenue
    basic_game.refresh_from_db()
    assert basic_game.phase == Game.Phase.FORUM


@pytest.mark.django_db
def test_governor_returns_to_rome_and_province_to_forum_when_term_moves_off_1(basic_game: Game):
    # Arrange
    gov, prov = _setup_for_returning(basic_game, term=1)

    # Act
    execute_effects_and_manage_actions(basic_game.id)

    # Assert
    prov.refresh_from_db()
    gov.refresh_from_db()
    assert prov.term == 0
    assert prov.governor is None
    assert gov.location == "Rome"
    basic_game.refresh_from_db()
    assert basic_game.phase == Game.Phase.FORUM


@pytest.mark.django_db
def test_returning_governor_keeps_corrupt_marker(basic_game: Game):
    # Arrange
    gov, prov = _setup_for_returning(basic_game, term=1, corrupt=True)

    # Act
    execute_effects_and_manage_actions(basic_game.id)

    # Assert
    gov.refresh_from_db()
    prov.refresh_from_db()
    assert gov.corrupt is True
    assert gov.location == "Rome"
    assert prov.governor is None


@pytest.mark.django_db
def test_garrison_legions_stay_with_province_on_return(basic_game: Game):
    # Arrange
    gov, prov = _setup_for_returning(basic_game, term=1, num_garrisons=1)

    garrison = Legion.objects.filter(game=basic_game, province=prov).first()
    assert garrison is not None

    # Act
    execute_effects_and_manage_actions(basic_game.id)

    # Assert
    prov.refresh_from_db()
    garrison.refresh_from_db()
    assert prov.governor is None
    assert garrison.province_id == prov.id


@pytest.mark.django_db
def test_rebel_governor_term_not_reduced(basic_game: Game):
    # Arrange
    gov, prov = _setup_for_returning(basic_game, term=2)
    gov.rebel = True
    gov.save()

    # Act
    execute_effects_and_manage_actions(basic_game.id)

    # Assert
    prov.refresh_from_db()
    assert prov.term == 2  # unchanged
    assert prov.governor_id == gov.id
