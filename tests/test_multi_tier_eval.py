from scripts.multi_tier_eval import (
    DEFAULT_TIERS,
    _limit_for_tier,
    _overall_release_passed,
    _tier1_passed,
)


def test_default_tiers_include_degraded_and_model_benchmark():
    names = [tier.name for tier in DEFAULT_TIERS]
    assert names == [
        "tier0-fixtures",
        "tier1a-openscore",
        "tier1b-musescore-com",
        "tier2-degraded",
        "tier3-model-benchmark",
    ]
    kinds = {tier.name: tier.kind for tier in DEFAULT_TIERS}
    assert kinds["tier2-degraded"] == "degrade"
    assert kinds["tier3-model-benchmark"] == "model_benchmark"


def test_tier1_lanes_do_not_require_tier0():
    by_name = {tier.name: tier for tier in DEFAULT_TIERS}
    assert by_name["tier1a-openscore"].requires_prior_tier is None
    assert by_name["tier1b-musescore-com"].requires_prior_tier is None
    assert by_name["tier2-degraded"].requires_prior_tier == "tier1a-openscore"
    assert by_name["tier3-model-benchmark"].requires_prior_tier == "tier1a-openscore"


def test_tier1_passed_requires_openscore_and_musescore_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.multi_tier_eval.REPO_ROOT",
        tmp_path,
    )
    manifests = tmp_path / "evaluation" / "manifests"
    manifests.mkdir(parents=True)
    manifests.joinpath("musescore-com-manual.local.json").write_text("{}", encoding="utf-8")

    assert _tier1_passed({"tier1a-openscore": True, "tier1b-musescore-com": True}) is True
    assert _tier1_passed({"tier1a-openscore": True, "tier1b-musescore-com": False}) is False
    assert _tier1_passed({"tier1a-openscore": False, "tier1b-musescore-com": True}) is False


def test_overall_release_requires_tier0_and_tier1(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.multi_tier_eval.REPO_ROOT",
        tmp_path,
    )
    manifests = tmp_path / "evaluation" / "manifests"
    manifests.mkdir(parents=True)
    manifests.joinpath("musescore-com-manual.local.json").write_text("{}", encoding="utf-8")

    assert (
        _overall_release_passed(
            {
                "tier0-fixtures": True,
                "tier1a-openscore": True,
                "tier1b-musescore-com": True,
            }
        )
        is True
    )
    assert (
        _overall_release_passed(
            {
                "tier0-fixtures": False,
                "tier1a-openscore": True,
                "tier1b-musescore-com": True,
            }
        )
        is False
    )
    assert (
        _overall_release_passed(
            {
                "tier0-fixtures": True,
                "tier1a-openscore": True,
                "tier1b-musescore-com": False,
            }
        )
        is False
    )


def test_full_gates_limits():
    by_name = {tier.name: tier for tier in DEFAULT_TIERS}
    assert _limit_for_tier(by_name["tier0-fixtures"], limit=5, full_gates=True) == 3
    assert _limit_for_tier(by_name["tier1a-openscore"], limit=5, full_gates=True) == 0
    assert _limit_for_tier(by_name["tier1b-musescore-com"], limit=5, full_gates=True) == 0
    assert _limit_for_tier(by_name["tier1a-openscore"], limit=5, full_gates=False) == 5
