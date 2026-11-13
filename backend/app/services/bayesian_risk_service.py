from web3 import Web3
from app import db
from app.models import (
    DefectEvent,
    InspectorVerdict,
    ExposureRecord,
    RiskAssessment,
)
from app.services.merkle_service import sha256_hex, build_merkle_tree
from app.services.exposure_service import compute_unit_level_exposure
from app.blockchain.contract_service import ContractService
from app.blockchain.transaction_service import TransactionService


CRITICALITY_BY_TYPE = {
    "LOT": 1.0,
    "BATCH": 1.25,
    "DISPATCH": 1.5,
}


def classify_risk_score(score: float) -> str:
    """
    Configurable risk thresholds for R(v) = S * C(v) * X_l(v) * P(D_l | E):
      R >= 3.5 -> RECALL_CANDIDATE
      R >= 2.0 -> QUARANTINE
      R >= 0.8 -> INSPECT
      R <  0.8 -> MONITOR
    """
    if score >= 3.5:
        return "RECALL_CANDIDATE"
    if score >= 2.0:
        return "QUARANTINE"
    if score >= 0.8:
        return "INSPECT"
    return "MONITOR"


def compute_bayesian_risk(
    event_code: str,
    prior_prob: float = 0.15,
    sensitivity: float = 0.92,
    false_support_prob: float = 0.08,
    anchor_onchain: bool = False,
) -> dict:
    """
    Module 6:
      LR_support    = sensitivity / false_support_prob
      LR_contradict = (1 - sensitivity) / (1 - false_support_prob)
      Odds(D | E)   = Odds(D) * prod_j LR_j
      P(D | E)      = Odds(D | E) / (1 + Odds(D | E))
      R(v)          = S * C(v) * X_l(v) * P(D_l | E)
    """
    if not (0.0 < prior_prob < 1.0):
        raise ValueError("Prior probability must be strictly between 0 and 1")
    if not (0.0 < sensitivity < 1.0) or not (0.0 < false_support_prob < 1.0):
        raise ValueError("Sensitivity and false_support_prob must be in (0, 1)")

    evt = DefectEvent.query.filter_by(event_code=event_code).first()
    if not evt:
        raise ValueError(f"Defect event {event_code} not found")

    exposures = ExposureRecord.query.filter_by(event_code=event_code).all()
    if not exposures:
        compute_unit_level_exposure(event_code)
        exposures = ExposureRecord.query.filter_by(event_code=event_code).all()

    verdicts = InspectorVerdict.query.filter_by(event_code=event_code).all()
    lr_support = sensitivity / false_support_prob
    lr_contradict = (1.0 - sensitivity) / (1.0 - false_support_prob)

    lr_product = 1.0
    for v in verdicts:
        if v.decision == "SUPPORT":
            lr_product *= lr_support
        elif v.decision == "CONTRADICT":
            lr_product *= lr_contradict

    prior_odds = prior_prob / (1.0 - prior_prob)
    posterior_odds = prior_odds * lr_product
    posterior_prob = posterior_odds / (1.0 + posterior_odds)

    RiskAssessment.query.filter_by(event_code=event_code).delete()

    assessments = []
    leaf_hashes = []
    for exp in exposures:
        c_v = CRITICALITY_BY_TYPE.get(exp.node_type, 1.0)
        r_score = float(evt.severity) * c_v * float(exp.exposure_fraction) * posterior_prob
        cls_label = classify_risk_score(r_score)
        rep_hash = sha256_hex(
            f"RISK|{event_code}|{exp.node_key}|{r_score:.6f}|{cls_label}"
        )
        leaf_hashes.append(rep_hash)

        ra = RiskAssessment(
            event_code=event_code,
            node_key=exp.node_key,
            severity_s=float(evt.severity),
            criticality_c=c_v,
            exposure_x=float(exp.exposure_fraction),
            prior_prob=prior_prob,
            likelihood_ratio_prod=lr_product,
            posterior_odds=posterior_odds,
            posterior_prob=posterior_prob,
            risk_score=r_score,
            classification=cls_label,
            report_hash=rep_hash,
        )
        db.session.add(ra)
        assessments.append(ra)

    report_root, _ = build_merkle_tree(leaf_hashes)
    db.session.commit()

    tx_hash = None
    if anchor_onchain and evt.onchain_tx_hash:
        cs = ContractService()
        if cs.bc.is_connected():
            try:
                tx_hash = cs.submit_risk_report_commitment(
                    event_id_bytes=Web3.keccak(text=event_code),
                    snapshot_version=evt.snapshot_version,
                    report_root_bytes=bytes.fromhex(report_root.removeprefix("0x")),
                )
                ts = TransactionService()
                rec = ts.record_and_verify_transaction(
                    tx_hash=tx_hash,
                    contract_name="ManufacturingRegistry",
                    function_name="registerRiskReportCommitment",
                    reference_id=event_code,
                )
                if rec.status == "CONFIRMED":
                    for a in assessments:
                        a.onchain_tx_hash = rec.tx_hash
                    db.session.commit()
            except Exception:
                pass

    return {
        "event_code": event_code,
        "bayesian_parameters": {
            "prior_probability": prior_prob,
            "sensitivity": sensitivity,
            "false_support_probability": false_support_prob,
            "lr_support": round(lr_support, 4),
            "lr_contradict": round(lr_contradict, 4),
            "verdict_count": len(verdicts),
            "likelihood_ratio_product": round(lr_product, 6),
            "posterior_odds": round(posterior_odds, 6),
            "posterior_probability": round(posterior_prob, 6),
        },
        "report_merkle_root": report_root,
        "onchain_tx_hash": tx_hash,
        "model_disclaimer": "Model-based Bayesian risk estimates guide operational triage and do not represent experimentally validated recall rates.",
        "assessments": [a.to_dict() for a in assessments],
    }
