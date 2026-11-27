import re
import os
import pytesseract

from PIL import Image, ImageOps
from datetime import datetime, date
from decimal import Decimal
from difflib import SequenceMatcher
from collections import Counter


# ==========================================
# 1. CONFIGURATION
# ==========================================

pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

KNOWN_MERCHANTS = {
    "Dollarama": ["dollarama"],
    "Loblaws": ["loblaws"],
    "Metro": ["metro"],
    "Food Basics": ["foodbasics"],
    "Green Fresh Supermarket": ["greenfresh"],
    "Best Buy": ["bestbuy"],
    "Walmart": ["walmart"],
    "Costco": ["costco"],
    "T&T Supermarket": [
        "t&tsupermarket",
        "tntsupermarket"
    ],
    "African BBQ House": ["africanbbqhouse"]
}

# Monetary values, including thousands separators
AMOUNT_PATTERN = (
    r"(?<![\d.,])"
    r"(?:\d{1,3}(?:,\d{3})+|\d+)"
    r"[.,]\d{2}"
    r"(?![\d.,])"
)

TOTAL_PATTERN = (
    r"\b(?:grand\s+total|amount\s+due|"
    r"total\s+due|total)\b"
)

PAYMENT_PATTERN = (
    r"\b(?:amount|debit|credit|mastercard|"
    r"visa|cash|cad|paid)\b"
)

EXCLUDED_PATTERN = (
    r"\b(?:sub\s*total|tax|hst|gst|savings?|"
    r"discounts?|change|items?|balance|"
    r"points|cashback|coupon|tendered)\b"
)

# ==========================================
# 2. IMAGE PREPROCESSING
# ==========================================

def preprocess_image(image):

    image = ImageOps.exif_transpose(image)

    return image.convert("RGB")


def detect_orientation(image):

    best_score = -1
    best_image = image

    for angle in [0, 90, 180, 270]:

        rotated = image.rotate(
            angle,
            expand=True
        )

        data = pytesseract.image_to_data(
            rotated,
            lang="eng",
            config="--oem 3 --psm 6",
            output_type=pytesseract.Output.DICT,
            timeout=30
        )

        scores = []

        for word, confidence in zip(
            data["text"],
            data["conf"]
        ):

            confidence = float(confidence)

            if word.strip() and confidence >= 0:
                scores.append(confidence)

        average_score = (
            sum(scores) / len(scores)
            if scores else 0
        )

        if average_score > best_score:

            best_score = average_score
            best_image = rotated

    return best_image


# ==========================================
# 3. TEXT RECOGNITION
# ==========================================

def extract_text(image, psm=6, scale=1):

    if scale != 1:

        width, height = image.size

        image = image.resize(
            (width * scale, height * scale),
            Image.Resampling.LANCZOS
        )

    return pytesseract.image_to_string(
        image,
        lang="eng",
        config=f"--oem 3 --psm {psm}",
        timeout=30
    )

# ==========================================
# 4. MERCHANT EXTRACTION
# ==========================================

def normalize_text(text):

    return re.sub(
        r"[^a-z0-9&]",
        "",
        text.lower()
    )


def extract_merchant(text):

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    normalized_text = normalize_text(text)

    # Method 1: Known merchant matching

    matches = set()

    for merchant, aliases in KNOWN_MERCHANTS.items():

        for alias in aliases:

            if normalize_text(alias) in normalized_text:
                matches.add(merchant)

    if len(matches) == 1:
        return next(iter(matches))

    if len(matches) > 1:
        return None

    # Method 2: Fuzzy matching on receipt header

    best_merchant = None
    best_score = 0

    for line in lines[:12]:

        normalized_line = normalize_text(line)

        if len(normalized_line) < 5:
            continue

        for merchant, aliases in KNOWN_MERCHANTS.items():

            for alias in aliases:

                score = SequenceMatcher(
                    None,
                    normalized_line,
                    normalize_text(alias)
                ).ratio()

                if score > best_score:

                    best_score = score
                    best_merchant = merchant

    if best_score >= 0.85:
        return best_merchant

    # Method 3: Unknown merchant detection

    ignored_words = (
        r"\b(?:welcome|thank|receipt|invoice|"
        r"customer|purchase|download|member|"
        r"phone|store\s*#|tax|hst|gst|"
        r"sale|total|subtotal|address|"
        r"join|survey|copy)\b"
    )

    for line in lines[:8]:

        if re.search(ignored_words, line, re.I):
            continue

        if not 3 <= len(line) <= 45:
            continue

        if re.search(r"\d", line):
            continue

        if not re.fullmatch(
            r"[A-Za-z][A-Za-z &.'-]+",
            line
        ):
            continue

        return line.strip().title()

    return None

# ==========================================
# 5. AMOUNT EXTRACTION
# ==========================================

def convert_amount(value):

    if "." in value and "," in value:

        value = value.replace(",", "")

    else:

        value = value.replace(",", ".")

    return Decimal(value)


def is_refund_receipt(text):

    # Explicit refund transaction labels
    refund_pattern = (
        r"(?im)^\s*(?:"
        r"refund(?:\s+receipt)?|"
        r"return\s+transaction|"
        r"(?:trans(?:action)?\.?\s*type|type)"
        r"\s*:\s*(?:refund|return)"
        r")\s*$"
    )

    if re.search(refund_pattern, text):
        return True

    # Negative monetary values on total lines
    for line in text.splitlines():

        if not re.search(TOTAL_PATTERN, line, re.I):
            continue

        if re.search(EXCLUDED_PATTERN, line, re.I):
            continue

        if re.search(
            r"(?:-\s*\$?\s*\d+[.,]\d{2}|"
            r"\$\s*-\s*\d+[.,]\d{2}|"
            r"\(\s*\$?\s*\d+[.,]\d{2}\s*\))",
            line
        ):
            return True

    return False


def extract_amount(text):

    if is_refund_receipt(text):
        return None

    lines = [
        line.strip().lower()
        for line in text.splitlines()
        if line.strip()
    ]

    totals = []
    payments = []

    for i, line in enumerate(lines):

        if re.search(EXCLUDED_PATTERN, line):
            continue

        if re.search(TOTAL_PATTERN, line):

            candidates = totals

        elif re.search(PAYMENT_PATTERN, line):

            candidates = payments

        else:
            continue

        matches = re.findall(
            AMOUNT_PATTERN,
            line
        )

        # Handle amounts on the following line
        if not matches and i + 1 < len(lines):

            next_line = lines[i + 1]

            if re.fullmatch(
                r"[\s$\d.,]+",
                next_line
            ):

                matches = re.findall(
                    AMOUNT_PATTERN,
                    next_line
                )

        # Handle PSM 11 reversed label/value order
        if not matches and i > 0:

            previous_line = lines[i - 1]

            if re.fullmatch(
                r"[\s$\d.,]+",
                previous_line
            ):

                matches = re.findall(
                    AMOUNT_PATTERN,
                    previous_line
                )

        for match in matches:

            amount = convert_amount(match)

            if amount > 0:
                candidates.append(amount)

    total_values = set(totals)
    payment_values = set(payments)

    confirmed = total_values.intersection(
        payment_values
    )

    # Total and payment agree
    if len(confirmed) == 1:

        return float(next(iter(confirmed)))

    # Only one distinct total
    if len(total_values) == 1 and not payment_values:

        return float(next(iter(total_values)))

    # Payment fallback
    if not total_values and len(payment_values) == 1:

        return float(next(iter(payment_values)))

    # Missing or conflicting amounts
    return None
# ==========================================
# 6. DATE EXTRACTION
# ==========================================

DATE_PATTERNS = [

    (
        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
        ["%Y-%m-%d"]
    ),

    (
        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b",
        ["%m-%d-%Y", "%d-%m-%Y"]
    ),

    (
        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2}\b",
        ["%y-%m-%d", "%m-%d-%y", "%d-%m-%y"]
    ),

    (
        r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b",
        ["%d %b %Y", "%d %B %Y"]
    ),

    (
        r"\b[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}\b",
        ["%b %d %Y", "%B %d %Y"]
    )
]


def extract_date(text):

    date_candidates = []

    for pattern, formats in DATE_PATTERNS:

        matches = re.findall(pattern, text)

        for match in matches:

            normalized = match.replace(
                "/", "-"
            ).replace(",", "")

            possible_dates = set()

            for date_format in formats:

                try:

                    parsed_date = datetime.strptime(
                        normalized,
                        date_format
                    ).date()

                    # Ignore unreasonable dates
                    if date(2000, 1, 1) <= parsed_date <= date.today():

                        possible_dates.add(
                            parsed_date.isoformat()
                        )

                except ValueError:

                    continue

            if possible_dates:

                date_candidates.append(possible_dates)

    if not date_candidates:
        return None

    # Find dates supported by unambiguous matches
    certain_dates = set()

    for candidates in date_candidates:

        if len(candidates) == 1:
            certain_dates.update(candidates)

    if len(certain_dates) == 1:

        return next(iter(certain_dates))

    if len(certain_dates) > 1:
        return None

    # Resolve ambiguous dates through agreement
    common_dates = set.intersection(
        *date_candidates
    )

    if len(common_dates) == 1:

        return next(iter(common_dates))

    return None

# ==========================================
# 7. STRUCTURED INFORMATION EXTRACTION
# ==========================================

def parse_receipt(text):

    merchant = extract_merchant(text)

    return {
        "merchant": merchant,
        "description": merchant,
        "amount": extract_amount(text),
        "transaction_date": extract_date(text),
        "transaction_type": "expense",
        "is_refund": is_refund_receipt(text)
    }

# ==========================================
# 8. RESULT SELECTION
# ==========================================

def select_field(results, field):

    values = [
        result[field]
        for result in results
        if result.get(field) is not None
    ]

    if not values:
        return None

    counts = Counter(values)

    value, count = counts.most_common(1)[0]

    # Stricter validation for financial amounts
    if field == "amount":

        if count < 2:
            return None

    # Require a strict majority of available values
    if count > len(values) / 2:
        return value

    # Missing or conflicting information
    return None

# ==========================================
# 9. COMPLETE OCR PIPELINE
# ==========================================

def process_receipt(image):

    image = preprocess_image(image)

    image = detect_orientation(image)

    configurations = [
        {"psm": 6, "scale": 1},
        {"psm": 6, "scale": 2},
        {"psm": 11, "scale": 1},
        {"psm": 11, "scale": 2}
    ]

    results = []
    errors = []

    for config in configurations:

        try:

            text = extract_text(
                image,
                psm=config["psm"],
                scale=config["scale"]
            )

            parsed = parse_receipt(text)
            print(
                f"PSM: {config['psm']} | "
                f"Scale: {config['scale']}"
            )

            print("Merchant:", parsed["merchant"])
            print("Amount:", parsed["amount"])
            print("Date:", parsed["transaction_date"])
            print("-" * 40)

            

            results.append(parsed)

        except (
            RuntimeError,
            pytesseract.TesseractError
        ) as error:

            errors.append(str(error))

    if not results:

        raise RuntimeError(
            "Unable to recognize receipt text."
        )

    merchant = select_field(results, "merchant")
    amount = select_field(results, "amount")
    transaction_date = select_field(
        results,
        "transaction_date"
    )

    refund_detected = any(
        result["is_refund"]
        for result in results
    )

    warnings = []

    if refund_detected:

        amount = None

        warnings.append(
            "Possible refund detected. "
            "Please review the transaction type and amount."
        )

    if merchant is None:

        warnings.append(
            "Merchant could not be reliably identified."
        )

    if amount is None:

        warnings.append(
            "Total amount could not be reliably identified."
        )

    if transaction_date is None:

        warnings.append(
            "Transaction date could not be reliably identified."
        )

    if errors:

        warnings.append(
            "Some OCR attempts could not be completed."
        )

    return {
        "merchant": merchant,
        "description": merchant,
        "amount": amount,
        "transaction_date": transaction_date,
        "transaction_type": (
            None if refund_detected else "expense"
        ),
        "is_refund": refund_detected,
        "requires_review": True,
        "warnings": warnings
    }