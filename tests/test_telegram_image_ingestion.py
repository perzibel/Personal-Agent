from pathlib import Path

from app.image_ingestion_service import ingest_telegram_image


def main():
    test_image = Path("C:\\Users\\User\\fileDetection\\Personal-Agent\\data\\test_image.jpg")

    if not test_image.exists():
        raise FileNotFoundError(f"Missing test image: {test_image}")

    result = ingest_telegram_image(
        local_path=test_image,
        telegram_file_id="test_file_id",
        telegram_file_unique_id="test_unique_id",
        caption="test caption",
        sender_id=12345,
    )

    print("Ingestion result:")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
