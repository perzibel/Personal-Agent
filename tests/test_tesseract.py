import pytesseract
from app.config import TESSERACT_CMD

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

print("Configured Tesseract path:", pytesseract.pytesseract.tesseract_cmd)
print("Tesseract version:")
print(pytesseract.get_tesseract_version())