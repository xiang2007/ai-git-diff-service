from src.errors import APIError
from unidiff.patch import PatchSet
from unidiff.errors import UnidiffParseError

def parse_diff(diff : str):
    try:
        patch = PatchSet(diff)
    except UnidiffParseError as exc:
        raise APIError("invalid_diff", "Diff is not a valid unified diff.") from exc
    if not patch or sum(len(f) for f in patch) == 0:
        raise APIError("invalid_diff", "Diff is not a valid unified diff.")
    return patch
