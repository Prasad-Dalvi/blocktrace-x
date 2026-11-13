// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";

/**
 * @title ManufacturingRegistry
 * @notice Anchors version-bound manufacturing snapshots and related commitments.
 */
contract ManufacturingRegistry is AccessControl {
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");
    bytes32 public constant QC_INSPECTOR_ROLE = keccak256("QC_INSPECTOR_ROLE");

    struct SnapshotCommitment {
        bytes32 rootHash;
        bytes32 metadataHash;
        bytes32 prevCommitment;
        uint256 timestamp;
        address registrar;
        bool exists;
    }

    struct DefectCommitment {
        bytes32 lotIdHash;
        uint256 snapshotVersion;
        bytes32 evidenceHash;
        uint8 severity;
        uint256 timestamp;
        address inspector;
        bool exists;
    }

    struct PropagationCommitment {
        uint256 snapshotVersion;
        bytes32 finalCursorHash;
        bytes32 affectedRootHash;
        uint256 affectedCount;
        uint256 timestamp;
        address operator;
        bool exists;
    }

    struct RiskReportCommitment {
        uint256 snapshotVersion;
        bytes32 reportRootHash;
        uint256 timestamp;
        address assessor;
        bool exists;
    }

    mapping(uint256 => SnapshotCommitment) private _snapshots;
    mapping(bytes32 => DefectCommitment) private _defects;
    mapping(bytes32 => PropagationCommitment) private _propagations;
    mapping(bytes32 => RiskReportCommitment) private _riskReports;
    uint256 public latestVersion;

    event SnapshotRegistered(
        uint256 indexed version,
        bytes32 indexed rootHash,
        bytes32 metadataHash,
        bytes32 prevCommitment,
        address indexed registrar,
        uint256 timestamp
    );

    event DefectCommitmentRegistered(
        bytes32 indexed eventId,
        bytes32 indexed lotIdHash,
        uint256 indexed snapshotVersion,
        bytes32 evidenceHash,
        uint8 severity,
        address inspector,
        uint256 timestamp
    );

    event PropagationCommitmentRegistered(
        bytes32 indexed eventId,
        uint256 indexed snapshotVersion,
        bytes32 finalCursorHash,
        bytes32 affectedRootHash,
        uint256 affectedCount,
        address indexed operator,
        uint256 timestamp
    );

    event RiskReportCommitmentRegistered(
        bytes32 indexed eventId,
        uint256 indexed snapshotVersion,
        bytes32 reportRootHash,
        address indexed assessor,
        uint256 timestamp
    );

    constructor(address admin) {
        require(admin != address(0), "Invalid admin address");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(REGISTRAR_ROLE, admin);
        _grantRole(QC_INSPECTOR_ROLE, admin);
    }

    function registerSnapshot(
        uint256 version,
        bytes32 rootHash,
        bytes32 metadataHash
    ) external onlyRole(REGISTRAR_ROLE) {
        require(version > 0, "Version must be > 0");
        require(rootHash != bytes32(0), "Empty rootHash");
        require(!_snapshots[version].exists, "Snapshot version already registered");

        bytes32 prev = version > 1 ? _snapshots[version - 1].rootHash : bytes32(0);

        _snapshots[version] = SnapshotCommitment({
            rootHash: rootHash,
            metadataHash: metadataHash,
            prevCommitment: prev,
            timestamp: block.timestamp,
            registrar: msg.sender,
            exists: true
        });

        if (version > latestVersion) {
            latestVersion = version;
        }

        emit SnapshotRegistered(
            version,
            rootHash,
            metadataHash,
            prev,
            msg.sender,
            block.timestamp
        );
    }

    function getSnapshot(uint256 version)
        external
        view
        returns (
            bytes32 rootHash,
            bytes32 metadataHash,
            uint256 timestamp,
            address registrar,
            bool exists
        )
    {
        SnapshotCommitment memory snap = _snapshots[version];
        return (
            snap.rootHash,
            snap.metadataHash,
            snap.timestamp,
            snap.registrar,
            snap.exists
        );
    }

    function getChainedSnapshot(uint256 version)
        external
        view
        returns (SnapshotCommitment memory)
    {
        return _snapshots[version];
    }

    function verifySnapshot(uint256 version, bytes32 rootHash)
        external
        view
        returns (bool)
    {
        SnapshotCommitment memory snap = _snapshots[version];
        return snap.exists && snap.rootHash == rootHash;
    }

    function registerDefectCommitment(
        bytes32 eventId,
        bytes32 lotIdHash,
        uint256 snapshotVersion,
        bytes32 evidenceHash,
        uint8 severity
    ) external onlyRole(QC_INSPECTOR_ROLE) {
        require(eventId != bytes32(0), "Empty eventId");
        require(lotIdHash != bytes32(0), "Empty lotIdHash");
        require(evidenceHash != bytes32(0), "Empty evidenceHash");
        require(severity >= 1 && severity <= 5, "Severity must be 1..5");
        require(_snapshots[snapshotVersion].exists, "Snapshot version does not exist");
        require(!_defects[eventId].exists, "Defect event already registered");

        _defects[eventId] = DefectCommitment({
            lotIdHash: lotIdHash,
            snapshotVersion: snapshotVersion,
            evidenceHash: evidenceHash,
            severity: severity,
            timestamp: block.timestamp,
            inspector: msg.sender,
            exists: true
        });

        emit DefectCommitmentRegistered(
            eventId,
            lotIdHash,
            snapshotVersion,
            evidenceHash,
            severity,
            msg.sender,
            block.timestamp
        );
    }

    function getDefectCommitment(bytes32 eventId)
        external
        view
        returns (
            bytes32 lotIdHash,
            uint256 snapshotVersion,
            bytes32 evidenceHash,
            uint8 severity,
            uint256 timestamp,
            address inspector,
            bool exists
        )
    {
        DefectCommitment memory d = _defects[eventId];
        return (
            d.lotIdHash,
            d.snapshotVersion,
            d.evidenceHash,
            d.severity,
            d.timestamp,
            d.inspector,
            d.exists
        );
    }

    function registerPropagationCommitment(
        bytes32 eventId,
        uint256 snapshotVersion,
        bytes32 finalCursorHash,
        bytes32 affectedRootHash,
        uint256 affectedCount
    ) external onlyRole(REGISTRAR_ROLE) {
        require(_defects[eventId].exists, "Defect event not anchored");
        require(_snapshots[snapshotVersion].exists, "Snapshot does not exist");
        require(affectedRootHash != bytes32(0), "Empty affectedRootHash");

        _propagations[eventId] = PropagationCommitment({
            snapshotVersion: snapshotVersion,
            finalCursorHash: finalCursorHash,
            affectedRootHash: affectedRootHash,
            affectedCount: affectedCount,
            timestamp: block.timestamp,
            operator: msg.sender,
            exists: true
        });

        emit PropagationCommitmentRegistered(
            eventId,
            snapshotVersion,
            finalCursorHash,
            affectedRootHash,
            affectedCount,
            msg.sender,
            block.timestamp
        );
    }

    function getPropagationCommitment(bytes32 eventId)
        external
        view
        returns (PropagationCommitment memory)
    {
        return _propagations[eventId];
    }

    function registerRiskReportCommitment(
        bytes32 eventId,
        uint256 snapshotVersion,
        bytes32 reportRootHash
    ) external onlyRole(REGISTRAR_ROLE) {
        require(_defects[eventId].exists, "Defect event not anchored");
        require(_snapshots[snapshotVersion].exists, "Snapshot does not exist");
        require(reportRootHash != bytes32(0), "Empty reportRootHash");

        _riskReports[eventId] = RiskReportCommitment({
            snapshotVersion: snapshotVersion,
            reportRootHash: reportRootHash,
            timestamp: block.timestamp,
            assessor: msg.sender,
            exists: true
        });

        emit RiskReportCommitmentRegistered(
            eventId,
            snapshotVersion,
            reportRootHash,
            msg.sender,
            block.timestamp
        );
    }

    function getRiskReportCommitment(bytes32 eventId)
        external
        view
        returns (RiskReportCommitment memory)
    {
        return _riskReports[eventId];
    }
}