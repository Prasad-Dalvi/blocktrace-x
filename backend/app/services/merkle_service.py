import hashlib


def sha256_bytes(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return "0x" + hashlib.sha256(data).hexdigest()


def build_merkle_tree(leaves_hex: list[str]) -> tuple[str, list[list[str]]]:
    """
    Deterministic binary Merkle tree over canonically ordered 32-byte hex leaves.
    If a level has an odd node count, the trailing node is duplicated.
    Returns (root_hex, levels_hex).
    """
    if not leaves_hex:
        empty_root = sha256_hex("BLOCKTRACEX_EMPTY_MERKLE_TREE")
        return empty_root, [[empty_root]]

    current = [bytes.fromhex(h.removeprefix("0x")) for h in leaves_hex]
    levels: list[list[str]] = [["0x" + b.hex() for b in current]]

    while len(current) > 1:
        next_level: list[bytes] = []
        for i in range(0, len(current), 2):
            left = current[i]
            right = current[i + 1] if i + 1 < len(current) else left
            next_level.append(sha256_bytes(left + right))
        current = next_level
        levels.append(["0x" + b.hex() for b in current])

    return "0x" + current[0].hex(), levels


def generate_merkle_proof(leaves_hex: list[str], target_index: int) -> list[dict]:
    if target_index < 0 or target_index >= len(leaves_hex):
        raise ValueError("Leaf index out of bounds")
    _, levels = build_merkle_tree(leaves_hex)
    proof = []
    idx = target_index
    for level in levels[:-1]:
        is_right = idx % 2 == 1
        sibling_idx = idx - 1 if is_right else (idx + 1 if idx + 1 < len(level) else idx)
        proof.append(
            {
                "position": "left" if is_right else "right",
                "hash": level[sibling_idx],
            }
        )
        idx //= 2
    return proof


def verify_merkle_proof(leaf_hex: str, proof: list[dict], expected_root_hex: str) -> bool:
    acc = bytes.fromhex(leaf_hex.removeprefix("0x"))
    for step in proof:
        sib = bytes.fromhex(step["hash"].removeprefix("0x"))
        if step["position"] == "left":
            acc = sha256_bytes(sib + acc)
        else:
            acc = sha256_bytes(acc + sib)
    return ("0x" + acc.hex()).lower() == expected_root_hex.lower()
