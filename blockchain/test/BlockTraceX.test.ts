import { expect } from "chai";
import { ethers } from "hardhat";

describe("BlockTrace-X Complete Stage 1-3 Smart Contract Suite", function () {
  async function deployFixture() {
    const [admin, manufacturer, supplier, buyer, qcInspector, arbitrator, thirdParty, outsider] =
      await ethers.getSigners();

    const ManufacturingRegistry = await ethers.getContractFactory("ManufacturingRegistry");
    const mfg = await ManufacturingRegistry.deploy(admin.address);

    const ClaimRegistry = await ethers.getContractFactory("ClaimRegistry");
    const claims = await ClaimRegistry.deploy(admin.address);

    const SupplyChainEscrow = await ethers.getContractFactory("SupplyChainEscrow");
    const escrow = await SupplyChainEscrow.deploy(admin.address, await claims.getAddress());

    await mfg.grantRole(await mfg.REGISTRAR_ROLE(), manufacturer.address);
    await mfg.grantRole(await mfg.QC_INSPECTOR_ROLE(), qcInspector.address);

    await claims.grantRole(await claims.CLAIM_FILER_ROLE(), buyer.address);
    await claims.grantRole(await claims.CLAIM_FILER_ROLE(), manufacturer.address);
    await claims.grantRole(await claims.SUPPLIER_ROLE(), supplier.address);
    await claims.grantRole(await claims.ARBITRATOR_ROLE(), arbitrator.address);

    await escrow.grantRole(await escrow.OPERATOR_ROLE(), manufacturer.address);
    await escrow.grantRole(await escrow.QC_ROLE(), qcInspector.address);

    return { mfg, claims, escrow, admin, manufacturer, supplier, buyer, qcInspector, arbitrator, thirdParty, outsider };
  }

  it("1. Executes full lifecycle: deposit -> ship -> receive -> QC fail -> complaint -> dispute -> settlement -> close", async function () {
    const { claims, escrow, manufacturer, supplier, buyer, qcInspector, arbitrator, thirdParty } =
      await deployFixture();

    const poId = ethers.id("PO-1001");
    const claimId = ethers.id("CLM-2023-114");
    const defectId = ethers.id("EVT-2023-114-01");
    const depositWei = ethers.parseEther("2.0");

    // Create & fund (10% Fr = 0.2 ETH, 90% Fa = 1.8 ETH)
    await escrow.connect(manufacturer).createEscrow(poId, buyer.address, supplier.address, ethers.id("PO-HASH"), depositWei);
    await escrow.connect(buyer).deposit(poId, 1000, { value: depositWei });

    // Ship & confirm receipt
    await escrow.connect(supplier).markShipment(poId, ethers.id("SHIP-001"));
    await escrow.connect(buyer).confirmReceipt(poId, ethers.id("RECV-001"));

    // Release 70% (1.4 ETH) milestone to supplier from Fa
    await escrow.connect(manufacturer).releaseSupplierPayment(poId, ethers.parseEther("1.4"));

    // QC Inspector registers QC FAIL and freezes remaining 0.6 ETH (0.4 Fa + 0.2 Fr -> Fd)
    await escrow.connect(qcInspector).registerQcResult(poId, false, ethers.parseEther("0.6"));
    let acct = await escrow.getEscrow(poId);
    expect(acct.fd).to.equal(ethers.parseEther("0.6"));
    expect(acct.fa).to.equal(0n);
    expect(acct.fr).to.equal(0n);

    // Buyer registers complaint claim & duplicate claim is rejected
    await claims.connect(buyer).registerClaim(claimId, poId, defectId, ethers.id("COMPLAINT-EVIDENCE"));
    await expect(
      claims.connect(buyer).registerClaim(claimId, poId, defectId, ethers.id("DUP"))
    ).to.be.revertedWithCustomError(claims, "ClaimAlreadyExists");

    // Supplier submits response & escalates to dispute
    await claims.connect(supplier).submitSupplierResponse(claimId, ethers.id("SUPPLIER-RESPONSE"), true);
    await escrow.connect(manufacturer).escalateToDispute(poId, claimId);

    // Arbitrator authorizes 3-way split of frozen 0.6 ETH:
    // 0.25 ETH buyer refund, 0.25 ETH supplier release, 0.10 ETH third-party lab compensation
    await claims.connect(arbitrator).authorizeSettlement(
      claimId,
      ethers.id("ARBITRATION-AWARD-01"),
      ethers.parseEther("0.25"),
      ethers.parseEther("0.25"),
      ethers.parseEther("0.10"),
      thirdParty.address
    );

    // Execute settlement & verify actual ETH transfer
    const buyerBalBefore = await ethers.provider.getBalance(buyer.address);
    await expect(escrow.connect(manufacturer).settleClaim(poId, claimId))
      .to.emit(escrow, "ClaimSettled");
    const buyerBalAfter = await ethers.provider.getBalance(buyer.address);
    expect(buyerBalAfter - buyerBalBefore).to.equal(ethers.parseEther("0.25"));

    // Replay settlement must revert
    await expect(
      escrow.connect(manufacturer).settleClaim(poId, claimId)
    ).to.be.revertedWithCustomError(escrow, "ReplaySettlementBlocked");

    // Close escrow & verify conservation invariant Dcum == Ps + Pb + Pc + Fd + Fr + Fa
    await expect(escrow.connect(manufacturer).closeEscrow(poId))
      .to.emit(escrow, "EscrowClosed");

    acct = await escrow.getEscrow(poId);
    expect(acct.ps).to.equal(ethers.parseEther("1.65"));
    expect(acct.pb).to.equal(ethers.parseEther("0.25"));
    expect(acct.pc).to.equal(ethers.parseEther("0.10"));
    expect(acct.fd).to.equal(0n);

    const [valid, dCum, sum] = await escrow.checkConservationInvariant(poId);
    expect(valid).to.equal(true);
    expect(dCum).to.equal(sum);
  });

  it("2. Blocks unauthorized settlement bypasses and insufficient bucket withdrawals", async function () {
    const { escrow, manufacturer, supplier, buyer, outsider } = await deployFixture();
    const poId = ethers.id("PO-2002");
    const depositWei = ethers.parseEther("1.0");

    await escrow.connect(manufacturer).createEscrow(poId, buyer.address, supplier.address, ethers.id("PO2"), depositWei);
    await escrow.connect(buyer).deposit(poId, 0, { value: depositWei });

    await expect(
      escrow.connect(outsider).releaseSupplierPayment(poId, ethers.parseEther("0.5"))
    ).to.be.reverted;

    await expect(
      escrow.connect(manufacturer).releaseSupplierPayment(poId, ethers.parseEther("1.5"))
    ).to.be.revertedWithCustomError(escrow, "InsufficientBucketFunds");

    await expect(
      escrow.connect(manufacturer).settleClaim(poId, ethers.id("UNAPPROVED-CLAIM"))
    ).to.be.revertedWithCustomError(escrow, "SettlementUnauthorized");
  });
});
