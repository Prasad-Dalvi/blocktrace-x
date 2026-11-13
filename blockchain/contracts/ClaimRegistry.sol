// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";

interface IClaimAuthorization {
    function isSettlementAuthorized(bytes32 claimId, bytes32 escrowId)
        external
        view
        returns (bool);

    function getAuthorizedPayouts(bytes32 claimId)
        external
        view
        returns (
            uint256 supplierPayout,
            uint256 buyerRefund,
            uint256 thirdPartyComp,
            address thirdPartyRecipient
        );
}

/**
 * @title ClaimRegistry
 * @notice Manages defect-linked claims, supplier responses, arbitration decisions,
 *         and tamper-evident settlement authorizations verified by SupplyChainEscrow.
 */
contract ClaimRegistry is AccessControl, IClaimAuthorization {
    bytes32 public constant CLAIM_FILER_ROLE = keccak256("CLAIM_FILER_ROLE");
    bytes32 public constant SUPPLIER_ROLE = keccak256("SUPPLIER_ROLE");
    bytes32 public constant ARBITRATOR_ROLE = keccak256("ARBITRATOR_ROLE");

    enum ClaimStatus {
        NONE,
        OPEN,
        RESPONDED,
        DISPUTED,
        AUTHORIZED,
        REJECTED
    }

    struct ClaimRecord {
        bytes32 escrowId;
        bytes32 defectEventId;
        bytes32 complaintEvidenceHash;
        bytes32 supplierResponseHash;
        bytes32 decisionCommitment;
        ClaimStatus status;
        address filer;
        uint256 supplierPayout;
        uint256 buyerRefund;
        uint256 thirdPartyComp;
        address thirdPartyRecipient;
        uint256 createdAt;
        uint256 authorizedAt;
        bool exists;
    }

    mapping(bytes32 => ClaimRecord) private _claims;

    error ClaimAlreadyExists(bytes32 claimId);
    error ClaimNotFound(bytes32 claimId);
    error InvalidClaimState(bytes32 claimId, ClaimStatus current);
    error InvalidCommitment();
    error InvalidThirdPartyRecipient();

    event ClaimRegistered(
        bytes32 indexed claimId,
        bytes32 indexed escrowId,
        bytes32 indexed defectEventId,
        bytes32 complaintEvidenceHash,
        address filer,
        uint256 timestamp
    );

    event SupplierResponded(
        bytes32 indexed claimId,
        bytes32 supplierResponseHash,
        bool disputed,
        address indexed responder,
        uint256 timestamp
    );

    event ClaimDisputed(
        bytes32 indexed claimId,
        address indexed actor,
        uint256 timestamp
    );

    event SettlementAuthorized(
        bytes32 indexed claimId,
        bytes32 indexed escrowId,
        bytes32 decisionCommitment,
        uint256 supplierPayout,
        uint256 buyerRefund,
        uint256 thirdPartyComp,
        address thirdPartyRecipient,
        address indexed authorizer
    );

    constructor(address admin) {
        require(admin != address(0), "Invalid admin");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(CLAIM_FILER_ROLE, admin);
        _grantRole(SUPPLIER_ROLE, admin);
        _grantRole(ARBITRATOR_ROLE, admin);
    }

    function registerClaim(
        bytes32 claimId,
        bytes32 escrowId,
        bytes32 defectEventId,
        bytes32 complaintEvidenceHash
    ) external onlyRole(CLAIM_FILER_ROLE) {
        if (_claims[claimId].exists) revert ClaimAlreadyExists(claimId);
        if (claimId == bytes32(0) || escrowId == bytes32(0) || defectEventId == bytes32(0)) {
            revert InvalidCommitment();
        }

        _claims[claimId] = ClaimRecord({
            escrowId: escrowId,
            defectEventId: defectEventId,
            complaintEvidenceHash: complaintEvidenceHash,
            supplierResponseHash: bytes32(0),
            decisionCommitment: bytes32(0),
            status: ClaimStatus.OPEN,
            filer: msg.sender,
            supplierPayout: 0,
            buyerRefund: 0,
            thirdPartyComp: 0,
            thirdPartyRecipient: address(0),
            createdAt: block.timestamp,
            authorizedAt: 0,
            exists: true
        });

        emit ClaimRegistered(
            claimId,
            escrowId,
            defectEventId,
            complaintEvidenceHash,
            msg.sender,
            block.timestamp
        );
    }

    function submitSupplierResponse(
        bytes32 claimId,
        bytes32 supplierResponseHash,
        bool escalateToDispute
    ) external onlyRole(SUPPLIER_ROLE) {
        ClaimRecord storage c = _claims[claimId];
        if (!c.exists) revert ClaimNotFound(claimId);
        if (c.status != ClaimStatus.OPEN) revert InvalidClaimState(claimId, c.status);
        if (supplierResponseHash == bytes32(0)) revert InvalidCommitment();

        c.supplierResponseHash = supplierResponseHash;
        c.status = escalateToDispute ? ClaimStatus.DISPUTED : ClaimStatus.RESPONDED;

        emit SupplierResponded(
            claimId,
            supplierResponseHash,
            escalateToDispute,
            msg.sender,
            block.timestamp
        );
    }

    function markDisputed(bytes32 claimId) external onlyRole(CLAIM_FILER_ROLE) {
        ClaimRecord storage c = _claims[claimId];
        if (!c.exists) revert ClaimNotFound(claimId);
        if (c.status != ClaimStatus.OPEN && c.status != ClaimStatus.RESPONDED) {
            revert InvalidClaimState(claimId, c.status);
        }
        c.status = ClaimStatus.DISPUTED;
        emit ClaimDisputed(claimId, msg.sender, block.timestamp);
    }

    function authorizeSettlement(
        bytes32 claimId,
        bytes32 decisionCommitment,
        uint256 supplierPayout,
        uint256 buyerRefund,
        uint256 thirdPartyComp,
        address thirdPartyRecipient
    ) external onlyRole(ARBITRATOR_ROLE) {
        ClaimRecord storage c = _claims[claimId];
        if (!c.exists) revert ClaimNotFound(claimId);
        if (
            c.status != ClaimStatus.OPEN &&
            c.status != ClaimStatus.RESPONDED &&
            c.status != ClaimStatus.DISPUTED
        ) {
            revert InvalidClaimState(claimId, c.status);
        }
        if (decisionCommitment == bytes32(0)) revert InvalidCommitment();
        if (thirdPartyComp > 0 && thirdPartyRecipient == address(0)) {
            revert InvalidThirdPartyRecipient();
        }

        c.decisionCommitment = decisionCommitment;
        c.supplierPayout = supplierPayout;
        c.buyerRefund = buyerRefund;
        c.thirdPartyComp = thirdPartyComp;
        c.thirdPartyRecipient = thirdPartyRecipient;
        c.status = ClaimStatus.AUTHORIZED;
        c.authorizedAt = block.timestamp;

        emit SettlementAuthorized(
            claimId,
            c.escrowId,
            decisionCommitment,
            supplierPayout,
            buyerRefund,
            thirdPartyComp,
            thirdPartyRecipient,
            msg.sender
        );
    }

    function isSettlementAuthorized(bytes32 claimId, bytes32 escrowId)
        external
        view
        override
        returns (bool)
    {
        ClaimRecord memory c = _claims[claimId];
        return (
            c.exists &&
            c.escrowId == escrowId &&
            c.status == ClaimStatus.AUTHORIZED
        );
    }

    function getAuthorizedPayouts(bytes32 claimId)
        external
        view
        override
        returns (
            uint256 supplierPayout,
            uint256 buyerRefund,
            uint256 thirdPartyComp,
            address thirdPartyRecipient
        )
    {
        ClaimRecord memory c = _claims[claimId];
        require(c.exists && c.status == ClaimStatus.AUTHORIZED, "Not authorized");
        return (
            c.supplierPayout,
            c.buyerRefund,
            c.thirdPartyComp,
            c.thirdPartyRecipient
        );
    }

    function getClaim(bytes32 claimId) external view returns (ClaimRecord memory) {
        if (!_claims[claimId].exists) revert ClaimNotFound(claimId);
        return _claims[claimId];
    }
}
