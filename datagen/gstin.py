"""GSTIN generation and validation utilities.

Implements the GSTIN checksum algorithm per the GST specification.
GSTIN format: 2-digit state code + 10-character PAN + 1 entity code + 1 'Z' + 1 checksum
Total: 15 characters.
"""

import random
import string

# State codes for GSTIN (first 2 digits)
STATE_CODES = {
    "01": "Jammu & Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman & Diu",
    "26": "Dadra & Nagar Haveli",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (old)",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman & Nicobar",
    "36": "Telangana",
    "37": "Andhra Pradesh (new)",
    "38": "Ladakh",
}

# Weights for checksum calculation (right to left, positions 1-14)
# Position 15 is the checksum character itself
WEIGHTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]

# Character map for checksum: 0-9, A-Z (36 characters)
CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CHAR_TO_VAL = {c: i for i, c in enumerate(CHARS)}


def compute_checksum(gstin_14: str) -> str:
    """Compute the GSTIN checksum character for a 14-character GSTIN prefix.

    Algorithm (per GST specification):
    1. Take the first 14 characters
    2. Map each character to its value (0-9 -> 0-9, A-Z -> 10-35)
    3. Multiply each value by its weight (position from right: 1, 2, 3, ...)
    4. Sum all products
    5. Compute remainder = sum % 36
    6. Checksum character = CHARS[remainder]

    Args:
        gstin_14: First 14 characters of GSTIN

    Returns:
        Checksum character (0-9 or A-Z)

    """
    if len(gstin_14) != 14:
        raise ValueError(f"Expected 14 characters, got {len(gstin_14)}")

    total = 0
    # Process right to left (position 1 is rightmost of the 14)
    for i, char in enumerate(reversed(gstin_14.upper())):
        if char not in CHAR_TO_VAL:
            raise ValueError(f"Invalid character in GSTIN: {char}")
        value = CHAR_TO_VAL[char]
        weight = WEIGHTS[i]
        total += value * weight

    remainder = total % 36
    return CHARS[remainder]


def validate_gstin(gstin: str) -> bool:
    """Validate a full 15-character GSTIN including checksum.

    Args:
        gstin: 15-character GSTIN

    Returns:
        True if valid, False otherwise

    """
    if not gstin or len(gstin) != 15:
        return False

    gstin = gstin.upper()

    # Validate character set
    for char in gstin:
        if char not in CHAR_TO_VAL:
            return False

    # Validate state code (first 2 chars)
    state_code = gstin[:2]
    if state_code not in STATE_CODES:
        return False

    # Validate PAN format (chars 3-12): 5 letters + 4 digits + 1 letter
    pan = gstin[2:12]
    if not (pan[:5].isalpha() and pan[5:9].isdigit() and pan[9].isalpha()):
        return False

    # Entity code (char 13): 1-9, A-Z (not 0)
    entity_code = gstin[12]
    if entity_code == "0":
        return False

    # Z character (char 14): must be 'Z'
    if gstin[13] != "Z":
        return False

    # Validate checksum (char 15)
    expected_checksum = compute_checksum(gstin[:14])
    return gstin[14] == expected_checksum


def generate_gstin(
    state_code: str,
    pan: str | None = None,
    entity_code: str | None = None,
    rng: random.Random | None = None,
) -> str:
    """Generate a valid GSTIN with correct checksum.

    Args:
        state_code: 2-digit state code (e.g., "29" for Karnataka)
        pan: 10-character PAN (5 letters + 4 digits + 1 letter). If None, generates random.
        entity_code: Entity code (1-9, A-Z). If None, generates random.
        rng: Random number generator for reproducibility

    Returns:
        15-character valid GSTIN

    """
    if state_code not in STATE_CODES:
        raise ValueError(f"Invalid state code: {state_code}")

    if rng is None:
        rng = random.Random()

    # Generate PAN if not provided
    if pan is None:
        # 5 letters + 4 digits + 1 letter
        letters = "".join(rng.choices(string.ascii_uppercase, k=5))
        digits = "".join(rng.choices(string.digits, k=4))
        last_letter = rng.choice(string.ascii_uppercase)
        pan = letters + digits + last_letter
    else:
        if len(pan) != 10:
            raise ValueError("PAN must be 10 characters")
        if not (pan[:5].isalpha() and pan[5:9].isdigit() and pan[9].isalpha()):
            raise ValueError("Invalid PAN format: must be 5 letters + 4 digits + 1 letter")

    # Generate entity code if not provided (1-9, A-Z, not 0)
    if entity_code is None:
        entity_choices = list("123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        entity_code = rng.choice(entity_choices)
    else:
        if entity_code not in "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            raise ValueError("Entity code must be 1-9 or A-Z")

    # Build 14-character prefix: state(2) + PAN(10) + entity(1) + Z(1)
    prefix = state_code + pan.upper() + entity_code + "Z"

    # Compute and append checksum
    checksum = compute_checksum(prefix)
    return prefix + checksum


def generate_random_gstin(rng: random.Random | None = None, state_code: str | None = None) -> str:
    """Generate a completely random valid GSTIN.

    Args:
        rng: Random number generator for reproducibility
        state_code: Optional specific state code

    Returns:
        15-character valid GSTIN

    """
    if rng is None:
        rng = random.Random()

    if state_code is None:
        state_code = rng.choice(list(STATE_CODES.keys()))

    return generate_gstin(state_code=state_code, rng=rng)


def parse_gstin(gstin: str) -> dict[str, str] | None:
    """Parse a GSTIN into its components.

    Args:
        gstin: 15-character GSTIN

    Returns:
        Dict with components or None if invalid

    """
    if not validate_gstin(gstin):
        return None

    gstin = gstin.upper()
    return {
        "state_code": gstin[:2],
        "state_name": STATE_CODES[gstin[:2]],
        "pan": gstin[2:12],
        "entity_code": gstin[12],
        "z_char": gstin[13],
        "checksum": gstin[14],
    }


# For property-based testing
def gstin_checksum_property(gstin_14: str) -> bool:
    """Property: compute_checksum should be deterministic."""
    return compute_checksum(gstin_14) == compute_checksum(gstin_14)


def gstin_validate_generated_property(state_code: str, pan: str, entity_code: str) -> bool:
    """Property: generated GSTIN should always validate."""
    gstin = generate_gstin(state_code, pan, entity_code)
    return validate_gstin(gstin)


if __name__ == "__main__":
    # Quick manual tests

    # Test known valid GSTINs (from public examples)
    test_gstins = [
        "29ABCDE1234F1Z5",  # Karnataka
        "07AAAAA0000A1Z5",  # Delhi
        "27AAAAA0000A1Z5",  # Maharashtra
    ]

    for gstin in test_gstins:
        valid = validate_gstin(gstin)
        parsed = parse_gstin(gstin)

    # Test generation
    rng = random.Random(42)
    for _i in range(5):
        gstin = generate_random_gstin(rng)
        valid = validate_gstin(gstin)
        parsed = parse_gstin(gstin)

    # Test checksum computation
    test_prefixes = [
        "29ABCDE1234F1Z",
        "07AAAAA0000A1Z",
        "27BBBBB1111B2Z",
    ]
    for prefix in test_prefixes:
        cs = compute_checksum(prefix)
        full = prefix + cs

