import pytesseract
from PIL import Image

# Configure Tesseract executable
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# Load receipt image
image = Image.open("sample_receipts/receipt_01.jpg")

# Extract raw text
text = pytesseract.image_to_string(image, lang="eng")

# Display extracted text
print(text)