from pathlib import Path
from PIL import Image
from pprint import pprint

from receipt_ocr import process_receipt

receipt_folder = Path("sample_receipts")

receipt_files = sorted(
    file for file in receipt_folder.iterdir()
    if file.suffix.lower() in (
        ".jpg", ".jpeg", ".png"
    )
)

for receipt in receipt_files:

    print("\n" + "=" * 60)
    print(f"RECEIPT: {receipt.name}")
    print("=" * 60)

    try:

        with Image.open(receipt) as image:

            result = process_receipt(image)

        pprint(result)

    except Exception as error:

        print(f"Error: {error}")