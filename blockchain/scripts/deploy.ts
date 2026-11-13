import { ethers, artifacts } from "hardhat";
import * as fs from "fs";
import * as path from "path";

async function main() {
  const [deployer, manufacturer, supplierS03, buyerBajaj, qcInspector, arbitrator] =
    await ethers.getSigners();

  console.log("Deploying BlockTrace-X Stage 3 contracts with account:", deployer.address);

  const ManufacturingRegistry = await ethers.getContractFactory("ManufacturingRegistry");
  const manufacturingRegistry = await ManufacturingRegistry.deploy(deployer.address);
  await manufacturingRegistry.waitForDeployment();
  const mfgAddress = await manufacturingRegistry.getAddress();

  const ClaimRegistry = await ethers.getContractFactory("ClaimRegistry");
  const claimRegistry = await ClaimRegistry.deploy(deployer.address);
  await claimRegistry.waitForDeployment();
  const claimAddress = await claimRegistry.getAddress();

  const SupplyChainEscrow = await ethers.getContractFactory("SupplyChainEscrow");
  const supplyChainEscrow = await SupplyChainEscrow.deploy(deployer.address, claimAddress);
  await supplyChainEscrow.waitForDeployment();
  const escrowAddress = await supplyChainEscrow.getAddress();

  // Grant roles
  await (await manufacturingRegistry.grantRole(await manufacturingRegistry.REGISTRAR_ROLE(), manufacturer.address)).wait();
  await (await manufacturingRegistry.grantRole(await manufacturingRegistry.QC_INSPECTOR_ROLE(), qcInspector.address)).wait();
  await (await manufacturingRegistry.grantRole(await manufacturingRegistry.QC_INSPECTOR_ROLE(), manufacturer.address)).wait();

  await (await claimRegistry.grantRole(await claimRegistry.CLAIM_FILER_ROLE(), buyerBajaj.address)).wait();
  await (await claimRegistry.grantRole(await claimRegistry.CLAIM_FILER_ROLE(), manufacturer.address)).wait();
  await (await claimRegistry.grantRole(await claimRegistry.SUPPLIER_ROLE(), supplierS03.address)).wait();
  await (await claimRegistry.grantRole(await claimRegistry.ARBITRATOR_ROLE(), arbitrator.address)).wait();

  await (await supplyChainEscrow.grantRole(await supplyChainEscrow.OPERATOR_ROLE(), manufacturer.address)).wait();
  await (await supplyChainEscrow.grantRole(await supplyChainEscrow.QC_ROLE(), qcInspector.address)).wait();
  await (await supplyChainEscrow.grantRole(await supplyChainEscrow.QC_ROLE(), manufacturer.address)).wait();

  // Create and fund PO-1001 Escrow with 2.0 ETH (separate local-testnet ETH value)
  const po1001Id = ethers.id("PO-1001");
  const poHash = ethers.keccak256(ethers.toUtf8Bytes("PO-1001|INR:200000|LOT:LOT-2023-114"));
  const targetWei = ethers.parseEther("2.0");

  await (
    await supplyChainEscrow.createEscrow(
      po1001Id,
      buyerBajaj.address,
      supplierS03.address,
      poHash,
      targetWei
    )
  ).wait();

  const depTx = await supplyChainEscrow
    .connect(buyerBajaj)
    .deposit(po1001Id, 1000, { value: targetWei }); // 10% Fr (0.2 ETH), 90% Fa (1.8 ETH)
  const depReceipt = await depTx.wait();

  const deploymentsDir = path.join(__dirname, "..", "deployments");
  if (!fs.existsSync(deploymentsDir)) {
    fs.mkdirSync(deploymentsDir, { recursive: true });
  }

  const mfgArtifact = await artifacts.readArtifact("ManufacturingRegistry");
  const claimArtifact = await artifacts.readArtifact("ClaimRegistry");
  const escrowArtifact = await artifacts.readArtifact("SupplyChainEscrow");

  const deploymentData = {
    network: "localhost",
    chainId: 31337,
    deployedAt: new Date().toISOString(),
    accounts: {
      admin: deployer.address,
      manufacturer: manufacturer.address,
      supplierS03: supplierS03.address,
      buyerBajaj: buyerBajaj.address,
      qcInspector: qcInspector.address,
      arbitrator: arbitrator.address,
    },
    contracts: {
      ManufacturingRegistry: {
        address: mfgAddress,
        abi: mfgArtifact.abi,
      },
      ClaimRegistry: {
        address: claimAddress,
        abi: claimArtifact.abi,
      },
      SupplyChainEscrow: {
        address: escrowAddress,
        abi: escrowArtifact.abi,
      },
    },
    initialTransactions: {
      po1001DepositTx: depReceipt?.hash,
    },
  };

  const outFile = path.join(deploymentsDir, "localhost.json");
  fs.writeFileSync(outFile, JSON.stringify(deploymentData, null, 2));
  console.log("Deployed Stage 3 contracts & saved ABIs to:", outFile);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
