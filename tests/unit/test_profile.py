import json

from nectar.profile import Profile


def test_profile():
    keys = ["profile.url", "profile.img"]
    values = ["http:", "foobar"]
    profile = Profile(keys, values)
    profile_ref = {"profile": {"url": "http:", "img": "foobar"}}
    assert profile == profile_ref
    assert json.loads(str(profile)) == profile_ref
    profile.update(profile_ref)
    assert profile == profile_ref
    profile.remove("profile.img")
    profile_ref = {"profile": {"url": "http:"}}
    assert profile == profile_ref
    profile = Profile({"foo": "bar"})
    assert profile == {"foo": "bar"}
