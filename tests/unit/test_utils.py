import os
from datetime import datetime

from ruamel.yaml import YAML

from nectar.utils import (
    addTzInfo,
    assets_from_string,
    construct_authorperm,
    construct_authorpermvoter,
    create_new_password,
    create_yaml_header,
    derive_beneficiaries,
    derive_permlink,
    derive_tags,
    formatTimedelta,
    formatTimeString,
    formatToTimeStamp,
    generate_password,
    import_coldcard_wif,
    import_pubkeys,
    make_patch,
    remove_from_dict,
    resolve_authorperm,
    resolve_authorpermvoter,
    resolve_root_identifier,
    sanitize_permlink,
    seperate_yaml_dict_from_body,
)


def test_construct_authorperm():
    assert construct_authorperm("A", "B") == "@A/B"
    assert construct_authorperm({"author": "A", "permlink": "B"}) == "@A/B"


def test_resolve_root_identifier():
    assert resolve_root_identifier("/a/@b/c") == ("@b/c", "a")


def test_construct_authorpermvoter():
    assert construct_authorpermvoter("A", "B", "C") == "@A/B|C"
    assert construct_authorpermvoter({"author": "A", "permlink": "B", "voter": "C"}) == "@A/B|C"
    assert construct_authorpermvoter({"authorperm": "A/B", "voter": "C"}) == "@A/B|C"


def test_assets_from_string():
    assert assets_from_string("USD:BTS") == ["USD", "BTS"]
    assert assets_from_string("BTSBOTS.S1:BTS") == ["BTSBOTS.S1", "BTS"]


def test_authorperm_resolve():
    assert resolve_authorperm("https://d.tube/#!/v/pottlund/m5cqkd1a") == ("pottlund", "m5cqkd1a")
    assert resolve_authorperm(
        "https://steemit.com/witness-category/@gtg/24lfrm-gtg-witness-log"
    ) == ("gtg", "24lfrm-gtg-witness-log")
    assert resolve_authorperm("@gtg/24lfrm-gtg-witness-log") == ("gtg", "24lfrm-gtg-witness-log")
    assert resolve_authorperm("https://busy.org/@gtg/24lfrm-gtg-witness-log") == (
        "gtg",
        "24lfrm-gtg-witness-log",
    )
    assert resolve_authorperm(
        "https://dlive.io/livestream/atnazo/61dd94c1-8ff3-11e8-976f-0242ac110003"
    ) == ("atnazo", "61dd94c1-8ff3-11e8-976f-0242ac110003")


def test_authorpermvoter_resolve():
    assert resolve_authorpermvoter("theaussiegame/cryptokittie-giveaway-number-2|test") == (
        "theaussiegame",
        "cryptokittie-giveaway-number-2",
        "test",
    )
    assert resolve_authorpermvoter(
        "thecrazygm/virtuelle-cloud-mining-ponzi-schemen-auch-bekannt-als-hypt|thecrazygm"
    ) == (
        "thecrazygm",
        "virtuelle-cloud-mining-ponzi-schemen-auch-bekannt-als-hypt",
        "thecrazygm",
    )


def test_sanitize_permlink():
    assert sanitize_permlink("aAf_0.12") == "aaf-0-12"
    assert sanitize_permlink("[](){}|") == ""


def test_derive_permlink():
    assert derive_permlink("Hello World").startswith("hello-world")
    assert derive_permlink("aAf_0.12").startswith("aaf-0-12")
    title = "[](){}"
    permlink = derive_permlink(title)
    assert not permlink.startswith("-")
    for char in title:
        assert char not in permlink
    assert len(derive_permlink("", parent_permlink=256 * "a")) == 256
    assert len(derive_permlink("", parent_permlink=256 * "a", parent_author="test")) == 256
    assert len(derive_permlink("a" * 1024)) == 256


def test_patch():
    assert make_patch("aa", "ab") == "@@ -1,2 +1,2 @@\n a\n-a\n+b\n"
    assert make_patch("aa\n", "ab\n") == "@@ -1,3 +1,3 @@\n a\n-a\n+b\n %0A\n"
    assert (
        make_patch("Hello!\n Das ist ein Test!\nEnd.\n", "Hello!\n This is a Test\nEnd.\n")
        == "@@ -5,25 +5,22 @@\n o!%0A \n-Da\n+Thi\n s is\n-t ein\n+ a\n  Test\n-!\n %0AEnd\n"
    )

    s1 = "test1\ntest2\ntest3\ntest4\ntest5\ntest6\n"
    s2 = "test1\ntest2\ntest3\ntest4\ntest5\ntest6\n"
    assert make_patch(s1, s2) == ""

    s2 = "test1\ntest2\ntest7\ntest4\ntest5\ntest6\n"
    assert make_patch(s1, s2) == "@@ -13,9 +13,9 @@\n test\n-3\n+7\n %0Ates\n"


def test_format_timedelta():
    now = datetime.now()
    assert formatTimedelta(now - now) == "0:00:00"


def test_remove_from_dict():
    a = {"a": 1, "b": 2}
    b = {"b": 2}
    assert remove_from_dict(a, ["b"], keep_keys=True) == {"b": 2}
    assert remove_from_dict(a, ["a"], keep_keys=False) == {"b": 2}
    assert remove_from_dict(b, ["b"], keep_keys=True) == {"b": 2}
    assert remove_from_dict(b, ["a"], keep_keys=False) == {"b": 2}
    assert remove_from_dict(b, [], keep_keys=True) == {}
    assert remove_from_dict(a, ["a", "b"], keep_keys=False) == {}


def test_format_datetime_to_timestamp():
    t = "1970-01-01T00:00:00"
    t = formatTimeString(t)
    assert formatToTimeStamp(t) == 0
    assert formatToTimeStamp("2018-07-10T10:08:39") == 1531217319
    assert formatToTimeStamp(datetime(2018, 7, 10, 10, 8, 39)) == 1531217319


def test_format_time_string():
    t = "2018-07-10T10:08:39"
    t = formatTimeString(t)
    t2 = addTzInfo(datetime(2018, 7, 10, 10, 8, 39))
    assert t == "2018-07-10T10:08:39"
    assert formatTimeString(t2) == t


def test_derive_beneficiaries():
    assert derive_beneficiaries("thecrazygm:10") == [{"account": "thecrazygm", "weight": 1000}]
    assert derive_beneficiaries("thecrazygm") == [{"account": "thecrazygm", "weight": 10000}]
    assert derive_beneficiaries("thecrazygm:30,thecrazygm:40") == [
        {"account": "thecrazygm", "weight": 7000}
    ]
    assert derive_beneficiaries("thecrazygm:30.00%,thecrazygm:40.00%") == [
        {"account": "thecrazygm", "weight": 7000}
    ]
    assert derive_beneficiaries("thecrazygm:30%, thecrazygm:40%") == [
        {"account": "thecrazygm", "weight": 7000}
    ]
    assert derive_beneficiaries("thecrazygm:30,thecrazygm") == [
        {"account": "thecrazygm", "weight": 10000}
    ]
    assert derive_beneficiaries(["thecrazygm:30", "thecrazygm"]) == [
        {"account": "thecrazygm", "weight": 10000}
    ]


def test_derive_tags():
    assert derive_tags("test1,test2") == ["test1", "test2"]
    assert derive_tags("test1, test2") == ["test1", "test2"]
    assert derive_tags("test1 test2") == ["test1", "test2"]


def test_seperate_yaml_dict_from_body():
    t = "---\npar1: data1\npar2: data2\npar3: 3\n---\n test ---"
    body, par = seperate_yaml_dict_from_body(t)
    assert par == {"par1": "data1", "par2": "data2", "par3": 3}
    assert body == " test ---"


def test_create_yaml_header():
    comment = {"title": "test", "author": "thecrazygm", "max_accepted_payout": 100}
    yaml_content = create_yaml_header(comment)
    yaml_safe = YAML(typ="safe")
    parameter = list(yaml_safe.load_all(yaml_content))[0]
    assert parameter["title"] == "test"
    assert parameter["author"] == "thecrazygm"
    assert parameter["max_accepted_payout"] == 100


def test_create_new_password():
    new_password = create_new_password()
    assert len(new_password) == 32
    assert any(c.islower() for c in new_password)
    assert any(c.isupper() for c in new_password)
    assert any(c.isdigit() for c in new_password)

    new_password2 = create_new_password()
    assert new_password != new_password2
    assert len(create_new_password(length=16)) == 16


def test_generate_password():
    assert generate_password("test", wif=0) == "test"
    assert (
        generate_password("test", wif=1) == "P5K2YUVmWfxbmvsNxCsfvArXdGXm7d5DC9pn4yD75k2UaSYgkXTh"
    )


def test_import_coldcard_wif():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "nectar", "data")
    file = os.path.join(data_dir, "drv-wif-idx100.txt")
    wif, path = import_coldcard_wif(file)
    assert wif == "L5K7x3Zs6jgY5jMovRzdgucWHmvuidyPj1f8ioCAzGjHMhjmL5EL"
    assert path == "m/83696968'/2'/100'"


def test_import_pubkeys():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "nectar", "data")
    file = os.path.join(data_dir, "pubkey.json")
    owner, active, posting, memo = import_pubkeys(file)
    assert owner == "STM51mq6zWEz3NGRYL8uMpJAe9c1qzf4ufh2ha4QqWzizqVrPL9Nq"
    assert active == "STM6oVMzJJJgSu3hV1DZBcLdMUJYj3Cs6kGXf6WVLP3HhgLgNkA5J"
    assert posting == "STM8XJdv7T36XhKRmPaodt8tqoeMbNgLrsiyweNESvnKqZWQQekCQ"
    assert memo == "STM87KR1HKDoLiC3dv3goE99KDqEocBi3br8vcop6DgrCTwJcWexH"
