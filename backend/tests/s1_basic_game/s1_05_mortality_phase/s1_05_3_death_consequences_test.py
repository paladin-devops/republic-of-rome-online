import pytest
from rorapp.classes.concession import Concession
from rorapp.helpers.kill_senator import kill_senator
from rorapp.models import Game, Legion, Province, Senator


@pytest.mark.django_db
def test_senator_death_releases_concessions(basic_game: Game):
    # Arrange
    game = basic_game
    senator = Senator.objects.get(game=game, family_name="Cornelius")
    senator.add_concession(Concession.MINING)
    senator.add_concession(Concession.LATIUM_TAX_FARMER)
    senator.save()

    # Act
    kill_senator(senator)

    # Assert
    game.refresh_from_db()
    assert "mining" in game.concessions
    assert "Latium tax farmer" in game.concessions
    senator.refresh_from_db()
    assert senator.concessions == []


@pytest.mark.django_db
def test_faction_leader_death_clears_status_items(basic_game: Game):
    # Arrange
    game = basic_game
    senator = Senator.objects.get(game=game, family_name="Cornelius")
    senator.add_title(Senator.Title.FACTION_LEADER)
    senator.add_status_item(Senator.StatusItem.CONSENT_REQUIRED)
    senator.save()

    # Act
    kill_senator(senator)

    # Assert
    senator.refresh_from_db()
    assert senator.status_items == []


@pytest.mark.django_db
def test_governor_death_returns_provinces_to_forum_and_clears_corrupt_rebel_markers(basic_game: Game):
    # Arrange
    game = basic_game
    senator = Senator.objects.get(game=game, family_name="Cornelius")
    province = Province.objects.create(
        game=game,
        name="Sicilia",
        governor=senator,
        term=2,
    )
    garrison = Legion.objects.create(
        game=game,
        number=25,
        province=province,
    )
    senator.corrupt = True
    senator.rebel = True
    senator.save()

    # Act
    kill_senator(senator)

    # Assert
    province.refresh_from_db()
    garrison.refresh_from_db()
    senator.refresh_from_db()
    assert province.governor is None
    assert garrison.province_id == province.id
    assert senator.corrupt is False
    assert senator.rebel is False
