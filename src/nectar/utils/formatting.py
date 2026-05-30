import ast
import json
import math
import re
import secrets
import string
import time as timenow
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ruamel.yaml import YAML

from nectargraphenebase.account import PasswordKey

timeFormat = "%Y-%m-%dT%H:%M:%S"
# https://github.com/matiasb/python-unidiff/blob/master/unidiff/constants.py#L37
# @@ (source offset, length) (target offset, length) @@ (section header)
RE_HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))?\ @@[ ]?(.*)$", flags=re.MULTILINE
)


def formatTime(t: Union[float, datetime, date, time]) -> Optional[str]:
    """Properly Format Time for permlinks"""
    if isinstance(t, float):
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y%m%dt%H%M%S%Z")
    if isinstance(t, (datetime, date, time)):
        return t.strftime("%Y%m%dt%H%M%S%Z")


def addTzInfo(
    t: Optional[Union[datetime, date, time]], timezone_str: str = "UTC"
) -> Optional[datetime]:
    """Returns a datetime object with tzinfo added
    Uses Python's built-in timezone when possible
    """
    if not t:
        return None

    # For non-UTC timezones, log a warning once and use UTC
    if timezone_str.upper() != "UTC":
        import logging

        log = logging.getLogger(__name__)
        log.warning(
            f"Non-UTC timezone '{timezone_str}' not supported without pytz. Using UTC instead."
        )
        timezone_str = "UTC"

    if isinstance(t, datetime):
        if getattr(t, "tzinfo", None) is None:
            t = t.replace(tzinfo=timezone.utc)
        return t
    elif isinstance(t, date) and not isinstance(t, datetime):
        return datetime.combine(t, time.min).replace(tzinfo=timezone.utc)
    elif isinstance(t, time):
        return datetime.combine(date.today(), t).replace(tzinfo=timezone.utc)

    return None


def formatTimeString(t: Union[str, datetime, date, time]) -> str:
    """Properly Format Time for permlinks"""
    if isinstance(t, (datetime, date, time)):
        # Convert date/time to datetime first if needed
        if isinstance(t, date) and not isinstance(t, datetime):
            t = datetime.combine(t, time.min)
        elif isinstance(t, time):
            t = datetime.combine(date.today(), t)
        return t.strftime(timeFormat)
    result = addTzInfo(datetime.strptime(t, timeFormat))
    if result is None:
        raise ValueError("Failed to add timezone info")
    return result.strftime(timeFormat)


def formatToTimeStamp(t: Union[datetime, date, time, str]) -> int:
    """Returns a timestamp integer

    :param datetime t: datetime object
    :return: Timestamp as integer
    """
    if isinstance(t, (datetime, date, time)):
        t_with_tz = addTzInfo(t)
        if t_with_tz is None:
            raise ValueError("Failed to add timezone info")
        t = t_with_tz
    else:
        t = formatTimeString(t)
    # Ensure we have a datetime object for subtraction
    if isinstance(t, str):
        t = datetime.strptime(t, timeFormat).replace(tzinfo=timezone.utc)
    elif isinstance(t, (date, time)) and not isinstance(t, datetime):
        if isinstance(t, date):
            t = datetime.combine(t, time.min).replace(tzinfo=timezone.utc)
        else:
            t = datetime.combine(date.today(), t).replace(tzinfo=timezone.utc)

    # At this point, t should be a datetime object
    if not isinstance(t, datetime):
        raise TypeError(f"Expected datetime object, got {type(t)}")

    epoch = addTzInfo(datetime(1970, 1, 1))
    if epoch is None:
        raise ValueError("Failed to add timezone info to epoch")
    return int((t - epoch).total_seconds())


def formatTimeFromNow(secs: int = 0) -> str:
    """Properly Format Time that is `x` seconds in the future

    :param int secs: Seconds to go in the future (`x>0`) or the
                     past (`x<0`)
    :return: Properly formated time for Graphene (`%Y-%m-%dT%H:%M:%S`)
    :rtype: str

    """
    return datetime.fromtimestamp(timenow.time() + int(secs), tz=timezone.utc).strftime(timeFormat)


def formatTimedelta(td: timedelta) -> str:
    """Format timedelta to String"""
    if not isinstance(td, timedelta):
        return ""
    days, seconds = td.days, td.seconds
    hours = days * 24 + seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours}:{str(minutes).zfill(2)}:{str(seconds).zfill(2)}"


def parse_time(block_time: str) -> datetime:
    """Take a string representation of time from the blockchain, and parse it
    into datetime object.
    """
    return datetime.strptime(block_time, timeFormat).replace(tzinfo=timezone.utc)


def assets_from_string(text: str) -> List[str]:
    """Correctly split a string containing an asset pair.

    Splits the string into two assets with the separator being on of the
    following: `:`, `/`, or `-`.
    """
    return re.split(r"[\-:\/]", text)


def sanitize_permlink(permlink: str) -> str:
    permlink = permlink.strip()
    permlink = re.sub(r"_|\s|\.", "-", permlink)
    permlink = re.sub(r"[^\w-]", "", permlink)
    permlink = re.sub(r"[^a-zA-Z0-9-]", "", permlink)
    permlink = permlink.lower()
    return permlink


def derive_permlink(
    title: str,
    parent_permlink: Optional[str] = None,
    parent_author: Optional[str] = None,
    max_permlink_length: int = 256,
    with_suffix: bool = True,
) -> str:
    """Derive a permlink from a comment title (for root level
    comments) or the parent permlink and optionally the parent
    author (for replies).

    """
    formatted_time = formatTime(datetime.now(timezone.utc))
    suffix = "-" + (formatted_time.lower() if formatted_time else "")
    if parent_permlink and parent_author:
        prefix = "re-" + sanitize_permlink(parent_author) + "-"
        if with_suffix:
            rem_chars = max_permlink_length - len(suffix) - len(prefix)
        else:
            rem_chars = max_permlink_length - len(prefix)
        body = sanitize_permlink(parent_permlink)[:rem_chars]
        if with_suffix:
            return prefix + body + suffix
        else:
            return prefix + body
    elif parent_permlink:
        prefix = "re-"
        if with_suffix:
            rem_chars = max_permlink_length - len(suffix) - len(prefix)
        else:
            rem_chars = max_permlink_length - len(prefix)
        body = sanitize_permlink(parent_permlink)[:rem_chars]
        if with_suffix:
            return prefix + body + suffix
        else:
            return prefix + body
    else:
        if with_suffix:
            rem_chars = max_permlink_length - len(suffix)
        else:
            rem_chars = max_permlink_length
        body = sanitize_permlink(title)[:rem_chars]
        if len(body) == 0:  # empty title or title consisted of only special chars
            return suffix[1:]  # use timestamp only, strip leading "-"
        if with_suffix:
            return body + suffix
        else:
            return body


def resolve_authorperm(identifier: str) -> Tuple[str, str]:
    """
    Parse an author/permlink identifier and return (author, permlink).

    Accepts plain "author/permlink" or "@author/permlink", site URLs containing "/@author/permlink",
    and dtube-style URLs containing "#!/v/<author>/<permlink>". Returns a 2-tuple of strings
    (author, permlink). Raises ValueError if the identifier cannot be parsed.
    """
    # without any http(s)
    match = re.match(r"@?([\w\-\.]*)/([\w\-]*)", identifier)
    if hasattr(match, "group"):
        return match.group(1), match.group(2)
    # dtube url
    match = re.match(r"([\w\-\.]+[^#?\s]+)/#!/v/?([\w\-\.]*)/([\w\-]*)", identifier)
    if hasattr(match, "group"):
        return match.group(2), match.group(3)
    # url
    match = re.match(r"([\w\-\.]+[^#?\s]+)/@?([\w\-\.]*)/([\w\-]*)", identifier)
    if not hasattr(match, "group"):
        raise ValueError("Invalid identifier")
    return match.group(2), match.group(3)


def construct_authorperm(*args: Any) -> str:
    """Create a post identifier from comment/post object or arguments.
    Examples:

        .. code-block:: python

            >>> from nectar.utils import construct_authorperm
            >>> print(construct_authorperm('username', 'permlink'))
            @username/permlink
            >>> print(construct_authorperm({'author': 'username', 'permlink': 'permlink'}))
            @username/permlink

    """
    username_prefix = "@"
    if len(args) == 1:
        op = args[0]
        author, permlink = op["author"], op["permlink"]
    elif len(args) == 2:
        author, permlink = args
    else:
        raise ValueError("construct_identifier() received unparsable arguments")

    return f"{username_prefix}{author}/{permlink}"


def resolve_root_identifier(url: str) -> Tuple[str, str]:
    m = re.match(r"/([^/]*)/@([^/]*)/([^#]*).*", url)
    if not m:
        return "", ""
    else:
        category = m.group(1)
        author = m.group(2)
        permlink = m.group(3)
        return construct_authorperm(author, permlink), category


def resolve_authorpermvoter(identifier: str) -> Tuple[str, str, str]:
    """Correctly split a string containing an authorpermvoter.

    Splits the string into author and permlink with the
    following separator: ``/`` and ``|``.
    """
    pos = identifier.find("|")
    if pos < 0:
        raise ValueError("Invalid identifier")
    [author, permlink] = resolve_authorperm(identifier[:pos])
    return author, permlink, identifier[pos + 1 :]


def construct_authorpermvoter(*args: Any) -> str:
    """Create a vote identifier from vote object or arguments.
    Examples:

        .. code-block:: python

            >>> from nectar.utils import construct_authorpermvoter
            >>> print(construct_authorpermvoter('username', 'permlink', 'voter'))
            @username/permlink|voter
            >>> print(construct_authorpermvoter({'author': 'username', 'permlink': 'permlink', 'voter': 'voter'}))
            @username/permlink|voter

    """
    username_prefix = "@"
    if len(args) == 1:
        op = args[0]
        if "authorperm" in op:
            authorperm, voter = op["authorperm"], op["voter"]
            [author, permlink] = resolve_authorperm(authorperm)
        else:
            author, permlink, voter = op["author"], op["permlink"], op["voter"]
    elif len(args) == 2:
        authorperm, voter = args
        [author, permlink] = resolve_authorperm(authorperm)
    elif len(args) == 3:
        author, permlink, voter = args
    else:
        raise ValueError("construct_identifier() received unparsable arguments")

    return f"{username_prefix}{author}/{permlink}|{voter}"


def reputation_to_score(rep: Union[str, int]) -> float:
    """Converts the account reputation value into the reputation score"""
    if isinstance(rep, str):
        rep = int(rep)
    if rep == 0:
        return 25.0
    score = max([math.log10(abs(rep)) - 9, 0])
    if rep < 0:
        score *= -1
    score = (score * 9.0) + 25.0
    return score


def remove_from_dict(
    obj: Any, keys: Optional[List[str]] = None, keep_keys: bool = True
) -> Dict[str, Any]:
    """Prune a class or dictionary of all but keys (keep_keys=True).
    Prune a class or dictionary of specified keys.(keep_keys=False).
    """
    if keys is None:
        keys = []
    if not isinstance(obj, dict):
        obj = dict(obj)
    if keep_keys:
        return {k: v for k, v in obj.items() if k in keys}
    else:
        return {k: v for k, v in obj.items() if k not in keys}


def make_patch(a: str, b: str) -> str:
    import diff_match_patch as dmp_module

    dmp = dmp_module.diff_match_patch()
    patch = dmp.patch_make(a, b)
    patch_text = dmp.patch_toText(patch)
    return patch_text


def findall_patch_hunks(body: Optional[str] = None) -> List[Tuple]:
    if body is None:
        return []
    return RE_HUNK_HEADER.findall(body)


def derive_beneficiaries(beneficiaries: Union[str, List[str]]) -> List[Dict[str, Any]]:
    """
    Parse beneficiaries and return a normalized, merged list of unique accounts with weights in basis points.

    Accepts a comma-separated string or list with items like "account:10", "@account:10%", or "account" (unknown
    percentage). Duplicate accounts are merged by summing their explicit percentages and any share of the remaining
    percentage allocated to unknown entries. Unknown entries are distributed equally across all unknown slots.

    Returns a list of dicts sorted by account name: [{"account": str, "weight": int_basis_points}]
    where weight is expressed in basis points (e.g., 1000 == 10%).
    """
    # Normalize input to list of entries
    entries = beneficiaries if isinstance(beneficiaries, list) else beneficiaries.split(",")

    # Collect known percentages and unknown slots per account
    accounts = {}
    total_known_bp = 0  # basis points (1% == 100)
    total_unknown_slots = 0

    for raw in entries:
        token = raw.strip()
        if not token:
            continue
        name_part = token.split(":")[0].strip()
        account = name_part[1:] if name_part.startswith("@") else name_part
        if account not in accounts:
            accounts[account] = {"known_bp": 0, "unknown_slots": 0}

        if ":" not in token:
            # Unknown slot for this account
            accounts[account]["unknown_slots"] += 1
            total_unknown_slots += 1
            continue

        # Parse percentage
        perc_str = token.split(":", 1)[1].strip()
        if perc_str.endswith("%"):
            perc_str = perc_str[:-1].strip()
        try:
            perc = float(perc_str)
        except Exception:
            # Treat unparsable as unknown slot
            accounts[account]["unknown_slots"] += 1
            total_unknown_slots += 1
            continue
        bp = int(perc * 100)
        accounts[account]["known_bp"] += bp
        total_known_bp += bp

    # Distribute remaining to unknown slots equally (in bp)
    remaining_bp = max(0, 10000 - total_known_bp)
    if total_unknown_slots > 0 and remaining_bp > 0:
        for account, data in accounts.items():
            slots = data["unknown_slots"]
            if slots > 0:
                share_bp = int((remaining_bp * slots) / total_unknown_slots)
                data["known_bp"] += share_bp

    # Build final list (unique accounts) and sort deterministically
    result = [{"account": acc, "weight": data["known_bp"]} for acc, data in accounts.items()]
    result.sort(key=lambda x: x["account"])
    return result


def derive_tags(tags: str) -> List[str]:
    tags_list = []
    if len(tags.split(",")) > 1:
        for tag in tags.split(","):
            tags_list.append(tag.strip())
    elif len(tags.split(" ")) > 1:
        for tag in tags.split(" "):
            tags_list.append(tag.strip())
    elif len(tags) > 0:
        tags_list.append(tags.strip())
    return tags_list


def seperate_yaml_dict_from_body(content: str) -> Tuple[str, Dict[str, Any]]:
    parameter = {}
    body = ""
    if len(content.split("---\n")) > 1:
        body = content[content.find("---\n", 1) + 4 :]
        yaml_content = content[content.find("---\n") + 4 : content.find("---\n", 1)]
        yaml = YAML(typ="safe")
        parameter = yaml.load(yaml_content)
        if not isinstance(parameter, dict):
            parameter = yaml.load(yaml_content.replace(":", ": ").replace("  ", " "))
    else:
        body = content
    return body, parameter


def create_yaml_header(
    comment: Dict[str, Any],
    json_metadata: Optional[Dict[str, Any]] = None,
    reply_identifier: Optional[str] = None,
) -> str:
    """
    Create a YAML front-matter header string from post/comment data and metadata.

    Builds a YAML block (string) beginning and ending with '---' that includes selected fields when present:
    - title (quoted)
    - permlink
    - author
    - "authored by" (from json_metadata["author"])
    - description (quoted)
    - canonical_url
    - app
    - last_update (from comment["last_update"] or comment["updated"])
    - max_accepted_payout
    - percent_hbd
    - community (added when json_metadata["tags"] exists and comment["category"] differs from the first tag)
    - tags (comma-separated list)
    - beneficiaries (comma-separated entries formatted as "account:XX.XX%"; weights are converted from parts-per-10000 to percent with two decimals)
    - reply_identifier

    Parameters:
        comment (dict): Source post/comment data. Expected keys used include
            "title", "permlink", "author", "last_update" or "updated",
            "max_accepted_payout", optional "percent_hbd", optional "category",
            and optional "beneficiaries" (list of {"account": str, "weight": int}).
        json_metadata (dict, optional): Parsed JSON metadata; may contain "author",
            "description", "canonical_url", "app", and "tags" (list of strings).
        reply_identifier (str or None, optional): If provided, added as "reply_identifier".

    Returns:
        str: The composed YAML front-matter block as a string.
    """
    if json_metadata is None:
        json_metadata = {}
    yaml_prefix = "---\n"
    if comment["title"] != "":
        yaml_prefix += f'title: "{comment["title"]}"\n'
    if "permlink" in comment:
        yaml_prefix += f"permlink: {comment['permlink']}\n"
    yaml_prefix += f"author: {comment['author']}\n"
    if "author" in json_metadata:
        yaml_prefix += f"authored by: {json_metadata['author']}\n"
    if "description" in json_metadata:
        yaml_prefix += f'description: "{json_metadata["description"]}"\n'
    if "canonical_url" in json_metadata:
        yaml_prefix += f"canonical_url: {json_metadata['canonical_url']}\n"
    if "app" in json_metadata:
        yaml_prefix += f"app: {json_metadata['app']}\n"
    if "last_update" in comment:
        yaml_prefix += f"last_update: {comment['last_update']}\n"
    elif "updated" in comment:
        yaml_prefix += f"last_update: {comment['updated']}\n"
    yaml_prefix += f"max_accepted_payout: {str(comment['max_accepted_payout'])}\n"
    if "percent_hbd" in comment:
        yaml_prefix += f"percent_hbd: {str(comment['percent_hbd'])}\n"
    if "tags" in json_metadata:
        if (
            len(json_metadata["tags"]) > 0
            and comment["category"] != json_metadata["tags"][0]
            and len(comment["category"]) > 0
        ):
            yaml_prefix += f"community: {comment['category']}\n"
        yaml_prefix += f"tags: {','.join(json_metadata['tags'])}\n"
    if "beneficiaries" in comment:
        beneficiaries = []
        for b in comment["beneficiaries"]:
            beneficiaries.append(f"{b['account']}:{b['weight'] / 10000 * 100:.2f}%")
        if len(beneficiaries) > 0:
            yaml_prefix += f"beneficiaries: {','.join(beneficiaries)}\n"
    if reply_identifier is not None:
        yaml_prefix += f"reply_identifier: {reply_identifier}\n"
    yaml_prefix += "---\n"
    return yaml_prefix


def load_dirty_json(dirty_json: str) -> Dict[str, Any]:
    regex_replace = [
        (r"([ \{,:\[])(u)?'([^']+)'", r'\1"\3"'),
        (r" False([, \}\]])", r" false\1"),
        (r" True([, \}\]])", r" true\1"),
    ]
    for r, s in regex_replace:
        dirty_json = re.sub(r, s, dirty_json)
    clean_json = json.loads(dirty_json)
    return clean_json


def create_new_password(length: int = 32) -> str:
    """Creates a random password containing alphanumeric chars with at least 1 number and 1 upper and lower char"""
    alphabet = string.ascii_letters + string.digits
    while True:
        import_password = "".join(secrets.choice(alphabet) for i in range(length))
        if (
            any(c.islower() for c in import_password)
            and any(c.isupper() for c in import_password)
            and any(c.isdigit() for c in import_password)
        ):
            break
    return import_password


def import_coldcard_wif(filename: Union[str, Path]) -> Tuple[str, str]:
    """Reads a exported coldcard Wif text file and returns the WIF and used path"""
    next_var = ""
    import_password = ""
    path = ""
    with open(filename) as fp:
        for line in fp:
            if line.strip() == "":
                continue
            if line.strip() == "WIF (privkey):":
                next_var = "wif"
                continue
            elif "Path Used" in line.strip():
                next_var = "path"
                continue
            if next_var == "wif":
                import_password = line.strip()
            elif next_var == "path":
                path = line
            next_var = ""
    return import_password, path.lstrip().replace("\n", "")


def generate_password(import_password: str, wif: int = 1) -> str:
    if wif > 0:
        password = import_password
        for _ in range(wif):
            pk = PasswordKey("", password, role="")
            password = str(pk.get_private())
        password = "P" + password
    else:
        password = import_password
    return password


def import_pubkeys(import_pub: Union[str, Path]) -> Tuple[str, str, str, str]:
    if not Path(import_pub).is_file():
        raise Exception(f"File {import_pub} does not exist!")
    with open(import_pub) as fp:
        pubkeys = fp.read()
    if pubkeys.find("\0") > 0:
        with open(import_pub, encoding="utf-16") as fp:
            pubkeys = fp.read()
    pubkeys = ast.literal_eval(pubkeys)
    owner = pubkeys["owner"]
    active = pubkeys["active"]
    posting = pubkeys["posting"]
    memo = pubkeys["memo"]
    return owner, active, posting, memo


def import_custom_json(jsonid: str, json_data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Returns a list of required authorities for a custom_json operation.

    Returns the author and required posting authorities for a custom_json operation.

    Args:
        jsonid: The id of the custom json (not used but kept for compatibility)
        json_data: The data of the custom json

    Returns:
        tuple with required author and posting authorities
    """
    try:
        if (
            isinstance(json_data, dict)
            and "required_auths" in json_data
            and "required_posting_auths" in json_data
        ):
            required_auths = json_data["required_auths"]
            required_posting_auths = json_data["required_posting_auths"]
            del json_data["required_auths"]
            del json_data["required_posting_auths"]
            return required_auths, required_posting_auths
        else:
            return [], []
    except (KeyError, ValueError, TypeError):
        return [], []
