from rorapp.models import Log, Province, Senator


def return_governors(game_id: int) -> None:
    """Implements §1.06.6 RETURNING GOVERNORS.

    Called from RedistributionDoneEffect (once the players have finished
    redistribution) so the logic runs exactly once at the end of the
    Revenue Phase, before the phase is advanced to FORUM.

    All current non-rebel governors have their term dial reduced by 1.
    Any whose dial moves off "1" are returned to Rome and their Province
    (plus any attached garrison legions) is returned to the Forum.
    The corrupt marker (if present) is preserved on the senator.
    """
    provinces = (
        Province.objects.filter(game=game_id, governor__isnull=False)
        .select_related("governor")
    )
    updated_senators = []
    updated_provinces = []
    for p in provinces:
        gov = p.governor
        if gov and gov.rebel:
            continue
        p.term = max(0, p.term - 1)
        if p.term < 1:
            if gov:
                gov.location = "Rome"
                updated_senators.append(gov)
                Log.create_object(
                    game_id=game_id,
                    text=f"{gov.display_name} returned from the {p.name} governorship.",
                )
            p.governor_id = None
            # TODO: Confirm if Legion's Province foreign key should be cleared,
            # or if Legion "stays with" Province after governor return
        updated_provinces.append(p)
    if updated_senators:
        Senator.objects.bulk_update(updated_senators, ["location"])
    if updated_provinces:
        Province.objects.bulk_update(updated_provinces, ["term", "governor"])
