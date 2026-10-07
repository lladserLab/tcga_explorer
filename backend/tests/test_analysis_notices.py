from app.analysis_notices import (
    COMPETING_RISK_ENDPOINTS,
    DSS_COMPETING_RISK_MESSAGE,
    ZSCORE_TRANSPORTABILITY_MESSAGE,
    build_analysis_diagnostics,
    competing_risk_message,
)


def _model(
    model_id: str,
    *,
    status: str = "completed",
    warnings: list[str] | None = None,
    reason: str | None = None,
) -> dict:
    return {
        "model": model_id,
        "label": model_id.replace("_", " ").title(),
        "status": status,
        "warnings": warnings or [],
        "reason": reason,
    }


def test_provenance_is_information_and_unrequested_adjustment_stays_auxiliary() -> None:
    notices, diagnostics = build_analysis_diagnostics(
        [
            "12 samples were excluded because overall survival was not usable.",
            "3 extra sample records from patients with multiple eligible barcodes were removed; one sample per patient was retained using TCGA biospecimen priority.",
        ],
        {
            "cox_models": [
                _model("univariable"),
                _model("stage_adjusted"),
            ]
        },
    )

    assert diagnostics["primary_result_model"] == "univariable"
    assert diagnostics["selected_adjusted_model"] is None
    assert diagnostics["selected_adjusted_status"] == "not_requested"
    assert diagnostics["cohort_information_count"] == 2
    assert diagnostics["model_caution_count"] == 0
    assert {notice["severity"] for notice in notices} == {"info"}


def test_only_requested_adjusted_model_caution_changes_selected_status() -> None:
    ph_message = "Global proportional hazards test p < 0.05; inspect time-varying effects."
    notices, diagnostics = build_analysis_diagnostics(
        [f"Cox model warning: User-adjusted model: {ph_message}"],
        {
            "clinical_adjustment": {"status": "requested"},
            "cox_models": [
                _model("univariable", warnings=["Auxiliary model warning."]),
                _model("user_adjusted", warnings=[ph_message]),
            ]
        },
    )

    assert diagnostics["selected_adjusted_status"] == "caution"
    assert diagnostics["selected_model_caution_count"] == 1
    assert diagnostics["model_caution_count"] == 2
    assert len([notice for notice in notices if notice["selected_model"]]) == 1


def test_auxiliary_model_caution_does_not_contaminate_clean_selected_model() -> None:
    _, diagnostics = build_analysis_diagnostics(
        [],
        {
            "clinical_adjustment": {"status": "requested"},
            "cox_models": [
                _model("univariable", warnings=["Auxiliary model warning."]),
                _model("user_adjusted"),
            ]
        },
    )

    assert diagnostics["selected_adjusted_status"] == "clean"
    assert diagnostics["selected_model_caution_count"] == 0
    assert diagnostics["model_caution_count"] == 1


def test_structured_model_warning_is_not_repeated_as_method_context() -> None:
    warning = (
        "Low-information Cox model: 4.00 events per fitted parameter "
        "(< 5). Interpret cautiously."
    )
    notices, diagnostics = build_analysis_diagnostics(
        [warning],
        {
            "continuous_analysis": {
                "linear_models": [
                    {
                        **_model("continuous_univariable", warnings=[warning]),
                        "information_diagnostics": {
                            "status": "severe",
                            "events_per_parameter": 4.0,
                            "severe_threshold": 5,
                        },
                    }
                ]
            }
        },
    )

    assert diagnostics["model_caution_count"] == 1
    assert len([notice for notice in notices if notice["category"] == "model"]) == 1
    assert not [
        notice
        for notice in notices
        if notice["scope"] == "context" and warning in notice["message"]
    ]


def test_missing_adjusted_model_is_not_evaluable_not_a_warning() -> None:
    notices, diagnostics = build_analysis_diagnostics(
        [],
        {
            "cox_models": [
                _model("univariable"),
                _model(
                    "stage_adjusted",
                    status="skipped",
                    reason="Ordinal stage had fewer than two observed scores.",
                ),
                _model(
                    "grade_adjusted",
                    status="skipped",
                    reason="Ordinal grade had fewer than two observed scores.",
                ),
            ]
        },
    )

    assert diagnostics["selected_adjusted_status"] == "not_requested"
    assert diagnostics["model_caution_count"] == 0
    availability = [notice for notice in notices if notice["category"] == "availability"]
    assert len(availability) == 1
    assert availability[0]["severity"] == "not_evaluable"


def test_combined_analysis_keeps_unadjusted_interaction_primary_without_request() -> None:
    _, diagnostics = build_analysis_diagnostics(
        [],
        {
            "combined_signature": {
                "signature_a": {"method": "mean"},
                "signature_b": {"method": "mean"},
            },
            "cox_models": [
                _model("stage_adjusted", status="skipped", reason="Requires two groups."),
            ],
            "signature_interaction_cox_models": [
                _model("signature_interaction"),
                _model("signature_interaction_stage_grade_adjusted"),
            ],
        },
    )

    assert diagnostics["primary_result_model_family"] == "interaction"
    assert diagnostics["primary_result_model"] == "signature_interaction"
    assert diagnostics["selected_adjusted_model"] is None


def test_single_analysis_keeps_unadjusted_continuous_model_primary_without_request() -> None:
    _, diagnostics = build_analysis_diagnostics(
        [],
        {
            "continuous_analysis": {
                "linear_models": [
                    _model("continuous_univariable"),
                    _model("continuous_stage_grade_adjusted"),
                ]
            },
            "cox_models": [
                _model("stage_grade_adjusted"),
            ],
        },
    )

    assert diagnostics["primary_result_model_family"] == "continuous"
    assert diagnostics["primary_result_model"] == "continuous_univariable"
    assert diagnostics["selected_adjusted_model"] is None


def test_user_requested_adjustment_prefers_exact_continuous_model() -> None:
    _, diagnostics = build_analysis_diagnostics(
        [],
        {
            "clinical_adjustment": {"status": "requested"},
            "continuous_analysis": {
                "linear_models": [
                    _model("continuous_stage_grade_adjusted"),
                    _model("continuous_user_adjusted"),
                ]
            },
            "cox_models": [
                _model("stage_grade_adjusted"),
                _model("user_adjusted"),
            ],
        },
    )

    assert diagnostics["selected_adjusted_status"] == "clean"
    assert diagnostics["selected_adjusted_model_family"] == "continuous"
    assert diagnostics["selected_adjusted_model"] == "continuous_user_adjusted"
    assert diagnostics["primary_result_model"] == "continuous_user_adjusted"


def test_unavailable_user_adjustment_is_not_replaced_by_auxiliary_model() -> None:
    notices, diagnostics = build_analysis_diagnostics(
        [],
        {
            "clinical_adjustment": {"status": "requested"},
            "continuous_analysis": {
                "linear_models": [
                    _model("continuous_stage_adjusted"),
                    _model(
                        "continuous_user_adjusted",
                        status="skipped",
                        reason="Fewer than 10 complete patients after clinical covariate filtering.",
                    ),
                ]
            },
        },
    )

    assert diagnostics["selected_adjusted_status"] == "not_evaluable"
    assert diagnostics["selected_adjusted_model"] is None
    assert any(
        notice["code"] == "adjusted_model_not_evaluable"
        and "user-requested" in notice["message"]
        for notice in notices
    )


def test_zscore_signature_notice_is_informational_and_exact() -> None:
    notices, diagnostics = build_analysis_diagnostics(
        [],
        {
            "endpoint": "OS",
            "signature": {"method": "zscore"},
        },
    )

    matching = [
        notice
        for notice in notices
        if notice["code"] == "zscore_run_specific_standardization"
    ]
    assert len(matching) == 1
    assert matching[0]["severity"] == "info"
    assert matching[0]["message"] == ZSCORE_TRANSPORTABILITY_MESSAGE
    assert diagnostics["selected_adjusted_status"] == "not_requested"


def test_combined_zscore_and_dss_notices_are_each_reported_once() -> None:
    notices, _ = build_analysis_diagnostics(
        [DSS_COMPETING_RISK_MESSAGE],
        {
            "endpoint": "DSS",
            "combined_signature": {
                "signature_a": {"method": "mean"},
                "signature_b": {"method": "zscore"},
            },
        },
    )

    assert sum(
        notice["message"] == ZSCORE_TRANSPORTABILITY_MESSAGE
        for notice in notices
    ) == 1
    assert sum(
        notice["message"] == DSS_COMPETING_RISK_MESSAGE
        for notice in notices
    ) == 1


def test_single_gene_os_has_no_endpoint_or_score_interpretation_notice() -> None:
    notices, _ = build_analysis_diagnostics(
        [],
        {
            "endpoint": "OS",
            "signature": {"method": "single"},
        },
    )

    codes = {notice["code"] for notice in notices}
    assert "zscore_run_specific_standardization" not in codes
    assert "competing_risk_estimand_context" not in codes


def test_all_competing_risk_endpoints_receive_one_estimand_notice() -> None:
    assert COMPETING_RISK_ENDPOINTS == {"DSS", "DFI", "PFI"}
    for endpoint in sorted(COMPETING_RISK_ENDPOINTS):
        notices, _ = build_analysis_diagnostics(
            [competing_risk_message(endpoint)],
            {
                "endpoint": endpoint,
                "signature": {"method": "single"},
            },
        )

        matching = [
            notice
            for notice in notices
            if notice["code"] == "competing_risk_estimand_context"
        ]
        assert len(matching) == 1
        assert matching[0]["message"] == competing_risk_message(endpoint)
        assert "Fine-Gray" in matching[0]["message"]
