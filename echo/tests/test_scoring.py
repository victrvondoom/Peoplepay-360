from echo.scoring import robust_score


def test_correlation_penalty_changes_apparent_consensus_score():
    score, correlation, confidence = robust_score(
        raw_score=94, apparent_support_count=8, provenance_root_count=1,
        mean_confidence=0.9,
    )
    assert (score, correlation, confidence) == (71.0, 21.0, 2.0)


def test_independent_roots_preserve_beta_as_robust_winner():
    alpha_raw, beta_raw = 94, 87
    alpha, _, _ = robust_score(raw_score=alpha_raw, apparent_support_count=8,
                               provenance_root_count=1, mean_confidence=0.9)
    beta, _, _ = robust_score(raw_score=beta_raw, apparent_support_count=3,
                              provenance_root_count=3, mean_confidence=0.9)
    assert alpha_raw > beta_raw  # raw score ranking
    assert beta > alpha  # correlation-aware score ranking
