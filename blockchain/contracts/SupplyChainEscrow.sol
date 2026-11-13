// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./ClaimRegistry.sol";

/**
 * @title SupplyChainEscrow
 * @notice Full-lifecycle native ETH escrow contract with six-bucket conservation:
 *         D_cum = Ps + Pb + Pc + Fd + Fr + Fa
 *
 * State Machine:
 *   CREATED -> FUNDED -> SHIPPED -> RECEIVED -> QC_PASSED -> SETTLED -> CLOSED
 *                                           \-> COMPLAINT -> DISPUTED -> SETTLED -> CLOSED
 */
contract SupplyChainEscrow is AccessControl, ReentrancyGuard {
    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");
    bytes32 public constant QC_ROLE = keccak256("QC_ROLE");

    enum EscrowStatus {
        NONE,
        CREATED,
        FUNDED,
        SHIPPED,
        RECEIVED,
        QC_PASSED,
        COMPLAINT,
        DISPUTED,
        SETTLED,
        CLOSED
    }

    struct EscrowAccount {
        address buyer;
        address supplier;
        bytes32 poHash;
        bytes32 shipmentHash;
        bytes32 receiptHash;
        uint256 targetAmount;
        uint256 dCum; // Cumulative deposits
        uint256 fa;   // Available funds
        uint256 fr;   // Warranty reserve
        uint256 fd;   // Disputed / frozen funds
        uint256 ps;   // Cumulative supplier payments
        uint256 pb;   // Cumulative buyer refunds
        uint256 pc;   // Cumulative third-party compensation
        EscrowStatus status;
        bool exists;
    }

    IClaimAuthorization public immutable claimRegistry;
    mapping(bytes32 => EscrowAccount) private _escrows;
    mapping(bytes32 => bool) public settledClaims;
    uint256 public totalActiveEscrowBalance;

    error EscrowAlreadyExists(bytes32 escrowId);
    error EscrowNotFound(bytes32 escrowId);
    error InvalidState(bytes32 escrowId, EscrowStatus current, EscrowStatus expected);
    error UnauthorizedCaller(address caller);
    error InsufficientBucketFunds(uint256 available, uint256 required);
    error ReplaySettlementBlocked(bytes32 claimId);
    error SettlementUnauthorized(bytes32 claimId, bytes32 escrowId);
    error ConservationInvariantViolated(uint256 dCum, uint256 bucketSum);
    error TransferFailed(address recipient, uint256 amount);

    event EscrowCreated(
        bytes32 indexed escrowId,
        address indexed buyer,
        address indexed supplier,
        bytes32 poHash,
        uint256 targetAmount
    );
    event EscrowDeposited(
        bytes32 indexed escrowId,
        address indexed depositor,
        uint256 amount,
        uint256 dCum,
        uint256 fa,
        uint256 fr
    );
    event ShipmentMarked(bytes32 indexed escrowId, bytes32 shipmentHash, address indexed actor);
    event ReceiptConfirmed(bytes32 indexed escrowId, bytes32 receiptHash, address indexed buyer);
    event QcResultRecorded(bytes32 indexed escrowId, bool passed, uint256 frozenAmount, address indexed inspector);
    event WarrantyReserved(bytes32 indexed escrowId, uint256 amount, uint256 fr, uint256 fa);
    event FundsFrozen(bytes32 indexed escrowId, uint256 amount, uint256 fd, uint256 fa);
    event DisputeOpened(bytes32 indexed escrowId, bytes32 indexed claimId);
    event SupplierPaid(bytes32 indexed escrowId, address indexed supplier, uint256 amount, uint256 ps);
    event BuyerRefunded(bytes32 indexed escrowId, address indexed buyer, uint256 amount, uint256 pb);
    event CompensationPaid(bytes32 indexed escrowId, address indexed recipient, uint256 amount, uint256 pc);
    event ClaimSettled(
        bytes32 indexed escrowId,
        bytes32 indexed claimId,
        uint256 supplierPaid,
        uint256 buyerRefunded,
        uint256 thirdPartyPaid
    );
    event EscrowClosed(bytes32 indexed escrowId, EscrowStatus finalStatus);

    constructor(address admin, address claimRegistryAddress) {
        require(admin != address(0), "Invalid admin");
        require(claimRegistryAddress != address(0), "Invalid ClaimRegistry");
        claimRegistry = IClaimAuthorization(claimRegistryAddress);
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(OPERATOR_ROLE, admin);
        _grantRole(QC_ROLE, admin);
    }

    function _assertConservation(EscrowAccount storage e) internal view {
        uint256 sumBuckets = e.ps + e.pb + e.pc + e.fd + e.fr + e.fa;
        if (e.dCum != sumBuckets) {
            revert ConservationInvariantViolated(e.dCum, sumBuckets);
        }
    }

    function createEscrow(
        bytes32 escrowId,
        address buyer,
        address supplier,
        bytes32 poHash,
        uint256 targetAmount
    ) external onlyRole(OPERATOR_ROLE) {
        if (escrowId == bytes32(0) || _escrows[escrowId].exists) {
            revert EscrowAlreadyExists(escrowId);
        }
        require(buyer != address(0) && supplier != address(0) && buyer != supplier, "Invalid parties");
        require(targetAmount > 0, "Zero target");

        _escrows[escrowId] = EscrowAccount({
            buyer: buyer,
            supplier: supplier,
            poHash: poHash,
            shipmentHash: bytes32(0),
            receiptHash: bytes32(0),
            targetAmount: targetAmount,
            dCum: 0,
            fa: 0,
            fr: 0,
            fd: 0,
            ps: 0,
            pb: 0,
            pc: 0,
            status: EscrowStatus.CREATED,
            exists: true
        });

        _assertConservation(_escrows[escrowId]);
        emit EscrowCreated(escrowId, buyer, supplier, poHash, targetAmount);
    }

    function deposit(bytes32 escrowId, uint256 warrantyReserveBps)
        external
        payable
        nonReentrant
    {
        EscrowAccount storage e = _escrows[escrowId];
        if (!e.exists) revert EscrowNotFound(escrowId);
        if (msg.sender != e.buyer && !hasRole(OPERATOR_ROLE, msg.sender)) {
            revert UnauthorizedCaller(msg.sender);
        }
        if (e.status == EscrowStatus.CLOSED || e.status == EscrowStatus.SETTLED) {
            revert InvalidState(escrowId, e.status, EscrowStatus.CREATED);
        }
        require(msg.value > 0 && warrantyReserveBps <= 5000, "Invalid deposit params");

        uint256 reserveShare = (msg.value * warrantyReserveBps) / 10000;
        uint256 availableShare = msg.value - reserveShare;

        e.dCum += msg.value;
        e.fr += reserveShare;
        e.fa += availableShare;
        totalActiveEscrowBalance += msg.value;

        if (e.status == EscrowStatus.CREATED) {
            e.status = EscrowStatus.FUNDED;
        }

        _assertConservation(e);
        emit EscrowDeposited(escrowId, msg.sender, msg.value, e.dCum, e.fa, e.fr);
    }

    function markShipment(bytes32 escrowId, bytes32 shipmentHash) external {
        EscrowAccount storage e = _escrows[escrowId];
        if (!e.exists) revert EscrowNotFound(escrowId);
        if (msg.sender != e.supplier && !hasRole(OPERATOR_ROLE, msg.sender)) {
            revert UnauthorizedCaller(msg.sender);
        }
        if (e.status != EscrowStatus.FUNDED) {
            revert InvalidState(escrowId, e.status, EscrowStatus.FUNDED);
        }
        e.shipmentHash = shipmentHash;
        e.status = EscrowStatus.SHIPPED;
        emit ShipmentMarked(escrowId, shipmentHash, msg.sender);
    }

    function confirmReceipt(bytes32 escrowId, bytes32 receiptHash) external {
        EscrowAccount storage e = _escrows[escrowId];
        if (!e.exists) revert EscrowNotFound(escrowId);
        if (msg.sender != e.buyer && !hasRole(OPERATOR_ROLE, msg.sender)) {
            revert UnauthorizedCaller(msg.sender);
        }
        if (e.status != EscrowStatus.SHIPPED) {
            revert InvalidState(escrowId, e.status, EscrowStatus.SHIPPED);
        }
        e.receiptHash = receiptHash;
        e.status = EscrowStatus.RECEIVED;
        emit ReceiptConfirmed(escrowId, receiptHash, msg.sender);
    }

    function registerQcResult(
        bytes32 escrowId,
        bool passed,
        uint256 freezeAmountOnFail
    ) external onlyRole(QC_ROLE) {
        EscrowAccount storage e = _escrows[escrowId];
        if (!e.exists) revert EscrowNotFound(escrowId);
        if (e.status != EscrowStatus.RECEIVED && e.status != EscrowStatus.FUNDED) {
            revert InvalidState(escrowId, e.status, EscrowStatus.RECEIVED);
        }

        if (passed) {
            e.status = EscrowStatus.QC_PASSED;
            emit QcResultRecorded(escrowId, true, 0, msg.sender);
        } else {
            uint256 unfrozen = e.fa + e.fr;
            if (freezeAmountOnFail > unfrozen) {
                revert InsufficientBucketFunds(unfrozen, freezeAmountOnFail);
            }
            if (e.fa >= freezeAmountOnFail) {
                e.fa -= freezeAmountOnFail;
            } else {
                uint256 rem = freezeAmountOnFail - e.fa;
                e.fa = 0;
                e.fr -= rem;
            }
            e.fd += freezeAmountOnFail;
            e.status = EscrowStatus.COMPLAINT;
            _assertConservation(e);
            emit QcResultRecorded(escrowId, false, freezeAmountOnFail, msg.sender);
        }
    }

    function allocateWarrantyReserve(bytes32 escrowId, uint256 amount)
        external
        onlyRole(OPERATOR_ROLE)
    {
        EscrowAccount storage e = _escrows[escrowId];
        if (!e.exists) revert EscrowNotFound(escrowId);
        if (e.fa < amount) revert InsufficientBucketFunds(e.fa, amount);
        e.fa -= amount;
        e.fr += amount;
        _assertConservation(e);
        emit WarrantyReserved(escrowId, amount, e.fr, e.fa);
    }

    function freezeDisputedFunds(bytes32 escrowId, uint256 amount)
        external
        onlyRole(OPERATOR_ROLE)
    {
        EscrowAccount storage e = _escrows[escrowId];
        if (!e.exists) revert EscrowNotFound(escrowId);
        uint256 unfrozen = e.fa + e.fr;
        if (unfrozen < amount) revert InsufficientBucketFunds(unfrozen, amount);

        if (e.fa >= amount) {
            e.fa -= amount;
        } else {
            uint256 rem = amount - e.fa;
            e.fa = 0;
            e.fr -= rem;
        }
        e.fd += amount;
        e.status = EscrowStatus.DISPUTED;
        _assertConservation(e);
        emit FundsFrozen(escrowId, amount, e.fd, e.fa);
    }

    function escalateToDispute(bytes32 escrowId, bytes32 claimId)
        external
        onlyRole(OPERATOR_ROLE)
    {
        EscrowAccount storage e = _escrows[escrowId];
        if (!e.exists) revert EscrowNotFound(escrowId);
        if (e.status != EscrowStatus.COMPLAINT && e.status != EscrowStatus.DISPUTED) {
            revert InvalidState(escrowId, e.status, EscrowStatus.COMPLAINT);
        }
        e.status = EscrowStatus.DISPUTED;
        emit DisputeOpened(escrowId, claimId);
    }

    function releaseSupplierPayment(bytes32 escrowId, uint256 amount)
        external
        onlyRole(OPERATOR_ROLE)
        nonReentrant
    {
        EscrowAccount storage e = _escrows[escrowId];
        if (!e.exists) revert EscrowNotFound(escrowId);
        if (e.fa < amount) revert InsufficientBucketFunds(e.fa, amount);

        e.fa -= amount;
        e.ps += amount;
        totalActiveEscrowBalance -= amount;
        _assertConservation(e);

        (bool sent, ) = payable(e.supplier).call{value: amount}("");
        if (!sent) revert TransferFailed(e.supplier, amount);
        emit SupplierPaid(escrowId, e.supplier, amount, e.ps);
    }

    function refundBuyer(bytes32 escrowId, uint256 amount)
        external
        onlyRole(OPERATOR_ROLE)
        nonReentrant
    {
        EscrowAccount storage e = _escrows[escrowId];
        if (!e.exists) revert EscrowNotFound(escrowId);
        if (e.fa < amount) revert InsufficientBucketFunds(e.fa, amount);

        e.fa -= amount;
        e.pb += amount;
        totalActiveEscrowBalance -= amount;
        _assertConservation(e);

        (bool sent, ) = payable(e.buyer).call{value: amount}("");
        if (!sent) revert TransferFailed(e.buyer, amount);
        emit BuyerRefunded(escrowId, e.buyer, amount, e.pb);
    }

    /**
     * @notice Executes claim settlement authorized in ClaimRegistry.
     *         Independently enforces replay protection and six-bucket conservation.
     */
    function settleClaim(bytes32 escrowId, bytes32 claimId)
        external
        onlyRole(OPERATOR_ROLE)
        nonReentrant
    {
        EscrowAccount storage e = _escrows[escrowId];
        if (!e.exists) revert EscrowNotFound(escrowId);
        if (settledClaims[claimId]) revert ReplaySettlementBlocked(claimId);
        if (!claimRegistry.isSettlementAuthorized(claimId, escrowId)) {
            revert SettlementUnauthorized(claimId, escrowId);
        }

        (
            uint256 supplierPayout,
            uint256 buyerRefund,
            uint256 thirdPartyComp,
            address thirdPartyRecipient
        ) = claimRegistry.getAuthorizedPayouts(claimId);

        uint256 totalRequired = supplierPayout + buyerRefund + thirdPartyComp;
        if (e.fd < totalRequired) revert InsufficientBucketFunds(e.fd, totalRequired);

        // Effects (Checks-Effects-Interactions)
        settledClaims[claimId] = true;
        e.fd -= totalRequired;
        e.ps += supplierPayout;
        e.pb += buyerRefund;
        e.pc += thirdPartyComp;
        totalActiveEscrowBalance -= totalRequired;

        if (e.fd == 0) {
            e.status = EscrowStatus.SETTLED;
        }

        _assertConservation(e);

        // Interactions
        if (supplierPayout > 0) {
            (bool okS, ) = payable(e.supplier).call{value: supplierPayout}("");
            if (!okS) revert TransferFailed(e.supplier, supplierPayout);
        }
        if (buyerRefund > 0) {
            (bool okB, ) = payable(e.buyer).call{value: buyerRefund}("");
            if (!okB) revert TransferFailed(e.buyer, buyerRefund);
        }
        if (thirdPartyComp > 0) {
            (bool okC, ) = payable(thirdPartyRecipient).call{value: thirdPartyComp}("");
            if (!okC) revert TransferFailed(thirdPartyRecipient, thirdPartyComp);
            emit CompensationPaid(escrowId, thirdPartyRecipient, thirdPartyComp, e.pc);
        }

        emit ClaimSettled(escrowId, claimId, supplierPayout, buyerRefund, thirdPartyComp);
    }

    function closeEscrow(bytes32 escrowId)
        external
        onlyRole(OPERATOR_ROLE)
        nonReentrant
    {
        EscrowAccount storage e = _escrows[escrowId];
        if (!e.exists) revert EscrowNotFound(escrowId);
        require(e.fd == 0, "Cannot close escrow with disputed funds");
        require(
            e.status == EscrowStatus.SETTLED || e.status == EscrowStatus.QC_PASSED,
            "Escrow not settled or QC passed"
        );

        // Release any remaining Fa + Fr to supplier upon clean closure
        uint256 remainingSupplierBalance = e.fa + e.fr;
        e.fa = 0;
        e.fr = 0;
        e.ps += remainingSupplierBalance;
        totalActiveEscrowBalance -= remainingSupplierBalance;
        e.status = EscrowStatus.CLOSED;

        _assertConservation(e);

        if (remainingSupplierBalance > 0) {
            (bool ok, ) = payable(e.supplier).call{value: remainingSupplierBalance}("");
            if (!ok) revert TransferFailed(e.supplier, remainingSupplierBalance);
        }

        emit EscrowClosed(escrowId, EscrowStatus.CLOSED);
    }

    function getEscrow(bytes32 escrowId)
        external
        view
        returns (EscrowAccount memory)
    {
        if (!_escrows[escrowId].exists) revert EscrowNotFound(escrowId);
        return _escrows[escrowId];
    }

    function checkConservationInvariant(bytes32 escrowId)
        external
        view
        returns (bool valid, uint256 dCum, uint256 bucketSum)
    {
        EscrowAccount memory e = _escrows[escrowId];
        if (!e.exists) revert EscrowNotFound(escrowId);
        uint256 sum = e.ps + e.pb + e.pc + e.fd + e.fr + e.fa;
        return (e.dCum == sum, e.dCum, sum);
    }
}
