from rorapp.helpers.governor_candidates import (
    get_eligible_governor_candidates,
    has_governor_election_work_remaining,
    has_vacant_forum_provinces,
    vacant_forum_provinces,
)
from rorapp.models import Game, Province, Senator

PROPOSAL_PREFIX = "Elect governor of "
PROPOSAL_PREFIX_PLURAL = "Elect governors of "
PAIR_SEPARATOR = " and "


def format_governor_pair(province_name: str, senator: Senator) -> str:
    return f"{province_name}: {senator.display_name}"


def format_governor_proposal(province_name: str, senator: Senator) -> str:
    return f"{PROPOSAL_PREFIX}{format_governor_pair(province_name, senator)}"


def format_grouped_governor_proposal(
    pairings: list[tuple[Province, Senator]],
) -> str:
    sorted_pairings = sorted(pairings, key=lambda pair: pair[0].name)
    body = PAIR_SEPARATOR.join(
        format_governor_pair(province.name, senator)
        for province, senator in sorted_pairings
    )
    if len(sorted_pairings) == 1:
        return f"{PROPOSAL_PREFIX}{body}"
    return f"{PROPOSAL_PREFIX_PLURAL}{body}"


def is_governor_proposal(proposal: str) -> bool:
    return proposal.startswith(PROPOSAL_PREFIX) or proposal.startswith(
        PROPOSAL_PREFIX_PLURAL
    )


def parse_governor_proposals(proposal: str) -> list[tuple[str, str]] | None:
    if proposal.startswith(PROPOSAL_PREFIX_PLURAL):
        body = proposal[len(PROPOSAL_PREFIX_PLURAL) :]
    elif proposal.startswith(PROPOSAL_PREFIX):
        body = proposal[len(PROPOSAL_PREFIX) :]
    else:
        return None

    pairings = []
    for part in body.split(PAIR_SEPARATOR):
        if ": " not in part:
            return None
        province_name, senator_name = part.rsplit(": ", 1)
        if not province_name or not senator_name:
            return None
        pairings.append((province_name, senator_name))
    return pairings


def parse_governor_proposal(proposal: str) -> tuple[str, str] | None:
    pairings = parse_governor_proposals(proposal)
    if not pairings or len(pairings) != 1:
        return None
    return pairings[0]


def defeated_governor_pairings(defeated_proposals: list[str]) -> set[str]:
    defeated = set()
    for proposal in defeated_proposals:
        if proposal in defeated:
            continue
        if proposal.startswith(PROPOSAL_PREFIX) and PAIR_SEPARATOR not in proposal:
            defeated.add(proposal[len(PROPOSAL_PREFIX) :])
            continue
        pairings = parse_governor_proposals(proposal)
        if pairings:
            for province_name, senator_name in pairings:
                defeated.add(f"{province_name}: {senator_name}")
    return defeated


def is_defeated_governor_pairing(
    province_name: str, senator: Senator, defeated_proposals: list[str]
) -> bool:
    pair = format_governor_pair(province_name, senator)
    return pair in defeated_governor_pairings(defeated_proposals)


def governor_field_name(province_name: str) -> str:
    return f"Governor for {province_name}"


def next_senate_sub_phase_after_prosecutions(game_id: int) -> str:
    senators = list(Senator.objects.filter(game_id=game_id, alive=True))
    if has_governor_election_work_remaining(game_id, senators):
        return Game.SubPhase.GOVERNOR_ELECTION
    return Game.SubPhase.OTHER_BUSINESS


def next_senate_sub_phase_after_governor_election(game_id: int) -> str:
    senators = list(Senator.objects.filter(game_id=game_id, alive=True))
    if has_governor_election_work_remaining(game_id, senators):
        return Game.SubPhase.GOVERNOR_ELECTION
    return Game.SubPhase.OTHER_BUSINESS


def assign_governor(province: Province, senator: Senator) -> None:
    province.governor = senator
    province.term = 3
    province.elected_this_turn = True
    province.save()

    senator.location = province.name
    senator.remove_status_item(Senator.StatusItem.NAMED_IN_PROPOSAL)
    senator.save()


def clear_governorship(province: Province) -> None:
    province.governor = None
    province.term = None
    province.elected_this_turn = False
    province.save()