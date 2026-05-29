import json
import logging
import os
import re

import click

from nectar import exceptions
from nectar.account import Account
from nectar.amount import Amount
from nectar.cli import cli
from nectar.cli.utils import export_trx, unlock_wallet
from nectar.comment import Comment
from nectar.community import Communities, Community
from nectar.imageuploader import ImageUploader
from nectar.instance import shared_blockchain_instance
from nectar.utils import (
    construct_authorperm,
    derive_beneficiaries,
    derive_permlink,
    derive_tags,
    make_patch,
    seperate_yaml_dict_from_body,
)
from nectar.version import version as __version__

log = logging.getLogger(__name__)


@cli.command()
@click.argument("post_id", nargs=1, metavar="POST")
@click.option("--weight", "-w", help="Vote weight (from 0.1 to 100.0)")
@click.option("--account", "-a", help="Voter account name")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def upvote(post_id, account, weight, export):
    """Upvote a post/comment

    POST is @author/permlink
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not weight:
        weight = hv.config["default_vote_weight"]
    else:
        weight = float(weight)
        if weight > 100:
            raise ValueError("Maximum vote weight is 100.0!")
        elif weight < 0:
            raise ValueError("Minimum vote weight is 0!")

    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    try:
        comment_obj = Comment(post_id, blockchain_instance=hv)
        tx = comment_obj.upvote(weight, voter=account)
    except exceptions.VotingInvalidOnArchivedPost:
        print("Post/Comment is older than 7 days! Did not upvote.")
        tx = {}
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("post_id", nargs=1, metavar="POST")
@click.option("--account", "-a", help="Account name")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def delete(post_id, account, export):
    """delete a post/comment

    POST is @author/permlink
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()

    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    try:
        comment_obj = Comment(post_id, blockchain_instance=hv)
        tx = comment_obj.delete(account=account)
    except exceptions.VotingInvalidOnArchivedPost:
        print("Could not delete post.")
        tx = {}
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("post_id", nargs=1, metavar="POST")
@click.option("--account", "-a", help="Downvoter account name")
@click.option("--weight", "-w", default=100, help="Downvote weight (from 0.1 to 100.0)")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def downvote(post_id, account, weight, export):
    """Downvote a post/comment

    POST is @author/permlink
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()

    weight = float(weight)
    if weight > 100:
        raise ValueError("Maximum downvote weight is 100.0!")
    elif weight < 0:
        raise ValueError("Minimum downvote weight is 0!")

    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    try:
        comment_obj = Comment(post_id, blockchain_instance=hv)
        tx = comment_obj.downvote(weight, voter=account)
    except exceptions.VotingInvalidOnArchivedPost:
        print("Post/Comment is older than 7 days! Did not downvote.")
        tx = {}
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("markdown_file", nargs=1)
@click.option("--account", "-a", help="Account are you posting from")
@click.option("--title", "-t", help="Title of the post")
@click.option("--permlink", help="permlink of the post (derived from title if not given)")
@click.option("--tags", help="Tags for this post (comma-seperated)")
@click.option("--reply_identifier", help="Permlink of the post to reply to")
@click.option("--community", help="Community name")
@click.option("--canonical_url", help="Canonical URL of this post")
@click.option(
    "--beneficiaries",
    help="Define beneficiaries (e.g. hive-nectar:5%,thecrazygm:5%)",
)
@click.option("--percent_hbd", type=int, help="Percent of HBD to pay out")
@click.option("--max_accepted_payout", help="Maximum accepted payout in USD")
@click.option(
    "--no-parse-body",
    "-n",
    help="Disable parsing of links, tags and images",
    is_flag=True,
    default=False,
)
@click.option(
    "--no-patch-on-edit",
    "-e",
    help="Disable patch posting on edits (when the permlink already exists)",
    is_flag=True,
    default=False,
)
@click.option("--export", help="When set, transaction is stored in a file")
def post(
    markdown_file,
    account,
    title,
    permlink,
    tags,
    reply_identifier,
    community,
    canonical_url,
    beneficiaries,
    percent_hbd,
    max_accepted_payout,
    no_parse_body,
    no_patch_on_edit,
    export,
):
    """broadcasts a post/comment. All image links which links to a file will be uploaded.
    The yaml header can contain:

    ---
    title: your title
    tags: tag1,tag2
    community: hive-100000
    beneficiaries: hive-nectar:5%,thecrazygm:5%
    ---

    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()

    with open(markdown_file) as f:
        content = f.read()
    body, parameter = seperate_yaml_dict_from_body(content)
    if title is not None:
        parameter["title"] = title
    if account is not None:
        parameter["author"] = account
    if tags is not None:
        parameter["tags"] = tags
    if permlink is not None:
        parameter["permlink"] = permlink
    if beneficiaries is not None:
        parameter["beneficiaries"] = beneficiaries
    if community is not None:
        parameter["community"] = community
    if reply_identifier is not None:
        parameter["reply_identifier"] = reply_identifier
    if percent_hbd is not None:
        parameter["percent_hbd"] = percent_hbd
    elif "percent-hbd" in parameter:
        parameter["percent_hbd"] = parameter["percent-hbd"]
    if max_accepted_payout is not None:
        parameter["max_accepted_payout"] = max_accepted_payout
    elif "max-accepted-payout" in parameter:
        parameter["max_accepted_payout"] = parameter["max-accepted-payout"]

    if canonical_url is not None:
        parameter["canonical_url"] = canonical_url

    if not unlock_wallet(hv):
        return
    tags = None
    if "tags" in parameter:
        tags = derive_tags(parameter["tags"])
    title = ""
    if "title" in parameter:
        title = parameter["title"]
    if "author" in parameter:
        author = parameter["author"]
    else:
        author = hv.config["default_account"]
    permlink = None
    if "permlink" in parameter:
        permlink = parameter["permlink"]
    reply_identifier = None
    if "reply_identifier" in parameter:
        reply_identifier = parameter["reply_identifier"]
    community = None
    if "community" in parameter:
        community = parameter["community"]
    if "parse_body" in parameter:
        parse_body = bool(parameter["parse_body"])
    else:
        parse_body = not no_parse_body
    max_accepted_payout = parameter.get("max_accepted_payout")
    percent_hbd = parameter.get("percent_hbd")
    comment_options = {}
    if max_accepted_payout is not None:
        if hv.backed_token_symbol not in max_accepted_payout:
            max_accepted_payout = str(
                Amount(float(max_accepted_payout), hv.backed_token_symbol, blockchain_instance=hv)
            )
        comment_options["max_accepted_payout"] = max_accepted_payout
    if percent_hbd is not None:
        comment_options["percent_hbd"] = percent_hbd
    beneficiaries = None
    if "beneficiaries" in parameter:
        beneficiaries = derive_beneficiaries(parameter["beneficiaries"])
        for b in beneficiaries:
            Account(b["account"], blockchain_instance=hv)

    if permlink is not None:
        try:
            comment = Comment(construct_authorperm(author, permlink), blockchain_instance=hv)
        except Exception:
            comment = None
    else:
        comment = None

    iu = ImageUploader(blockchain_instance=hv)
    for link in list(
        re.findall(r'!\[[^"\'@\]\(]*\]\([^"\'@\(\)]*\.(?:png|jpg|jpeg|gif|png|svg)\)', body)
    ):
        image = link.split("(")[1].split(")")[0]
        image_name = link.split("![")[1].split("]")[0]
        if image[:4] == "http":
            continue
        if hv.unsigned:
            continue
        basepath = os.path.dirname(markdown_file)
        if os.path.exists(image):
            tx = iu.upload(image, author, image_name)
            body = body.replace(image, tx["url"])
        elif os.path.exists(os.path.join(basepath, image)):
            tx = iu.upload(image, author, image_name)
            body = body.replace(image, tx["url"])

    if comment is None and permlink is None and reply_identifier is None:
        permlink = derive_permlink(title, with_suffix=False)
        try:
            comment = Comment(construct_authorperm(author, permlink), blockchain_instance=hv)
        except Exception:
            comment = None
    if comment is None:
        json_metadata = {}
    else:
        json_metadata = comment.json_metadata
    if "authored_by" in parameter:
        json_metadata["authored_by"] = parameter["authored_by"]
    if "description" in parameter:
        json_metadata["description"] = parameter["description"]
    if "canonical_url" in parameter:
        json_metadata["canonical_url"] = parameter["canonical_url"]
    else:
        json_metadata["canonical_url"] = hv.config["default_canonical_url"] or "https://hive.blog"

    if "canonical_url" in json_metadata and json_metadata["canonical_url"].find("@") < 0:
        if json_metadata["canonical_url"][-1] != "/":
            json_metadata["canonical_url"] += "/"
        if json_metadata["canonical_url"][:8] != "https://":
            json_metadata["canonical_url"] = "https://" + json_metadata["canonical_url"]
        if community is None:
            json_metadata["canonical_url"] += tags[0] + "/@" + author + "/" + permlink
        else:
            json_metadata["canonical_url"] += community + "/@" + author + "/" + permlink

    if comment is None or no_patch_on_edit:
        if reply_identifier is None and (len(tags) == 0 or tags is None):
            raise ValueError("Tags must not be empty!")
        tx = hv.post(
            title,
            body,
            author=author,
            permlink=permlink,
            reply_identifier=reply_identifier,
            community=community,
            tags=tags,
            json_metadata=json_metadata,
            comment_options=comment_options,
            beneficiaries=beneficiaries,
            parse_body=parse_body,
            app="hive-nectar/%s" % (__version__),
        )
    else:
        patch_text = make_patch(comment.body, body)
        if patch_text == "":
            print("No changes on post body detected.")
        else:
            print(patch_text)
        edit_ok = click.prompt("Should I broadcast %s [y/n]" % (str(permlink)))
        if edit_ok not in ["y", "ye", "yes"]:
            return
        tx = hv.post(
            title,
            patch_text,
            author=author,
            permlink=permlink,
            reply_identifier=reply_identifier,
            community=community,
            tags=tags,
            json_metadata=json_metadata,
            parse_body=False,
            app="hive-nectar/%s" % (__version__),
        )
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("authorperm", nargs=1)
@click.argument("body", nargs=1)
@click.option("--account", "-a", help="Account are you posting from")
@click.option("--title", "-t", help="Title of the post")
@click.option("--export", "-e", help="When set, transaction is stored in a file")
def reply(authorperm, body, account, title, export):
    """replies to a comment"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()

    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return

    if title is None:
        title = ""
    tx = hv.post(
        title,
        body,
        json_metadata=None,
        author=account,
        reply_identifier=authorperm,
        app="hive-nectar/%s" % (__version__),
    )
    export_trx(tx, export)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("identifier", nargs=1)
@click.option("--account", "-a", help="Reblog as this user")
def reblog(identifier, account):
    """Reblog an existing post"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    acc = Account(account, blockchain_instance=hv)
    post = Comment(identifier, blockchain_instance=hv)
    tx = post.reblog(account=acc)
    tx = json.dumps(tx, indent=4)
    print(tx)


@cli.command()
@click.argument("image", nargs=1)
@click.option("--account", "-a", help="Account name")
@click.option("--image-name", "-n", help="Image name")
def uploadimage(image, account, image_name):
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if not unlock_wallet(hv):
        return
    iu = ImageUploader(blockchain_instance=hv)
    tx = iu.upload(image, account, image_name)
    if image_name is None:
        print("![](%s)" % tx["url"])
    else:
        print("![{}]({})".format(image_name, tx["url"]))


@cli.command()
@click.argument("permlink", nargs=-1)
@click.option("--account", "-a", help="Account are you posting from")
@click.option(
    "--save",
    "-s",
    help="Saves markdown in current directoy as date_permlink.md",
    is_flag=True,
    default=False,
)
@click.option("--export", "-e", default=None, help="Export markdown to given a md-file name")
def download(permlink, account, save, export):
    """Download body with yaml header"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if account is None:
        account = hv.config["default_account"]
    account = Account(account, blockchain_instance=hv)
    if len(permlink) == 0:
        permlink = []
        progress_length = account.virtual_op_count()
        print("Reading post history...")
        last_index = 0
        with click.progressbar(length=progress_length) as bar:
            for h in account.history(only_ops=["comment"]):
                if h["parent_author"] != "":
                    continue
                if h["author"] != account["name"]:
                    continue
                if h["permlink"] in permlink:
                    continue
                else:
                    permlink.append(h["permlink"])
                    bar.update(h["index"] - last_index)
                    last_index = h["index"]

    for p in permlink:
        if p[0] == "@":
            authorperm = p
        elif os.path.exists(p):
            with open(p) as f:
                content = f.read()
            body, parameter = seperate_yaml_dict_from_body(content)
            if "author" in parameter and "permlink" in parameter:
                authorperm = construct_authorperm(parameter["author"], parameter["permlink"])
            else:
                authorperm = construct_authorperm(account["name"], p)
        else:
            authorperm = construct_authorperm(account["name"], p)
        if len(permlink) > 1:
            print(authorperm)
        comment = Comment(authorperm, blockchain_instance=hv)
        if comment.parent_author != "" and comment.parent_permlink != "":
            reply_identifier = construct_authorperm(comment.parent_author, comment.parent_permlink)
        else:
            reply_identifier = None

        yaml_prefix = "---\n"
        if comment["title"] != "":
            yaml_prefix += 'title: "%s"\n' % comment["title"]
        yaml_prefix += "permlink: %s\n" % comment["permlink"]
        yaml_prefix += "author: %s\n" % comment["author"]
        if "author" in comment.json_metadata:
            yaml_prefix += "authored by: %s\n" % comment.json_metadata["author"]
        if "description" in comment.json_metadata:
            yaml_prefix += 'description: "%s"\n' % comment.json_metadata["description"]
        if "canonical_url" in comment.json_metadata:
            yaml_prefix += "canonical_url: %s\n" % comment.json_metadata["canonical_url"]
        if "app" in comment.json_metadata:
            yaml_prefix += "app: %s\n" % comment.json_metadata["app"]
        if "last_update" in comment.json():
            yaml_prefix += "last_update: %s\n" % comment.json()["last_update"]
        else:
            yaml_prefix += "last_update: %s\n" % comment.json()["updated"]
        yaml_prefix += "max_accepted_payout: %s\n" % str(comment["max_accepted_payout"])
        if "percent_hbd" in comment:
            yaml_prefix += "percent_hbd: %s\n" % str(comment["percent_hbd"])
        if "tags" in comment.json_metadata:
            if (
                len(comment.json_metadata["tags"]) > 0
                and comment["category"] != comment.json_metadata["tags"][0]
                and len(comment["category"]) > 0
            ):
                yaml_prefix += "community: %s\n" % comment["category"]
            yaml_prefix += "tags: %s\n" % ",".join(comment.json_metadata["tags"])
        if "beneficiaries" in comment:
            beneficiaries = []
            for b in comment["beneficiaries"]:
                beneficiaries.append("{}:{:.2f}%".format(b["account"], b["weight"] / 10000 * 100))
            if len(beneficiaries) > 0:
                yaml_prefix += "beneficiaries: %s\n" % ",".join(beneficiaries)
        if reply_identifier is not None:
            yaml_prefix += "reply_identifier: %s\n" % reply_identifier
        yaml_prefix += "---\n"
        if save or export is not None:
            if export is None or len(permlink) > 0:
                export = (
                    comment.json()["created"].replace(":", "-") + "_" + comment["permlink"] + ".md"
                )
            if export[-3:] != ".md":
                export += ".md"

            with open(export, "w", encoding="utf-8") as f:
                f.write(yaml_prefix + comment["body"])
        else:
            print(yaml_prefix + comment["body"])


@cli.command()
@click.argument("markdown-file", nargs=1)
@click.option("--account", "-a", help="Account are you posting from")
@click.option("--title", "-t", help="Title of the post")
@click.option("--tags", "-g", help="A komma separated list of tags to go with the post.")
@click.option("--community", "-c", help=" Name of the community (optional)")
@click.option(
    "--beneficiaries", "-b", help="Post beneficiaries (komma separated, e.g. a:10%,b:20%)"
)
@click.option("--percent-hbd", "-h", help="50% HBD/50% HP is 10000 (default), 100% HP is 0")
@click.option("--max-accepted-payout", "-m", help="Default is 1000000.000 [HBD]")
@click.option(
    "--no-parse-body",
    "-n",
    help="Disable parsing of links, tags and images",
    is_flag=True,
    default=False,
)
def createpost(
    markdown_file,
    account,
    title,
    tags,
    community,
    beneficiaries,
    percent_hbd,
    max_accepted_payout,
    no_parse_body,
):
    """Creates a new markdown file with YAML header"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()

    if account is None:
        account = input("author: ")
    if title is None:
        title = input("title: ")
    if tags is None:
        tags = input("tags (comma seperated): ")
    if community is None:
        community_found = False
        while not community_found:
            community_name = input("community account (name or title): ")
            try:
                community = Community(community_name)
            except Exception:
                c = Communities(limit=1000)
                comm_cand = c.search_title(community_name)
                if len(comm_cand) == 0:
                    print("No community could be found!")
                    continue
                print(comm_cand.printAsTable())
                index = input("Enter community Nr:")
                if int(index) - 1 >= len(comm_cand):
                    continue
                community = comm_cand[int(index) - 1]
            ret = input(
                "Selected community: {} - {} [yes/no]? ".format(
                    community["name"], community["title"]
                )
            )
            if ret in ["y", "yes"]:
                community_found = True
        community = community["name"]

    if beneficiaries is None:
        beneficiaries = input(
            "beneficiaries (komma separated, e.g. a:10%,b:20%) [return to skip]: "
        )
    if percent_hbd is None:
        ret = None
        while ret is None:
            ret = input("50% or 100% Hive Power as post reward [50 or 100]? ")
            if ret not in ["50", "100"]:
                ret = None
        if ret == "50":
            percent_hbd = 10000
        else:
            percent_hbd = 0

    if max_accepted_payout is None:
        max_accepted_payout = input("max accepted payout [return to skip]: ")
    yaml_prefix = "---\n"
    yaml_prefix += 'title: "%s"\n' % title
    yaml_prefix += "author: %s\n" % account
    yaml_prefix += "tags: %s\n" % tags
    yaml_prefix += "percent_hbd: %d\n" % percent_hbd
    if community is not None and community != "":
        yaml_prefix += "community: %s\n" % community
    if beneficiaries is not None and beneficiaries != "":
        yaml_prefix += "beneficiaries: %s\n" % beneficiaries
    if max_accepted_payout is not None and max_accepted_payout != "":
        yaml_prefix += "max_accepted_payout: %s\n" % max_accepted_payout
    yaml_prefix += "---\n"
    with open(markdown_file, "w", encoding="utf-8") as f:
        f.write(yaml_prefix)
