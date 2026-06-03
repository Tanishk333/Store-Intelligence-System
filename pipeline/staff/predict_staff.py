import argparse
from pathlib import Path

import torch
from PIL import Image

from pipeline.staff.model import CLASSES, load_checkpoint, preprocessing


def predict(model_path: str, image_path: str) -> dict:
    model = load_checkpoint(model_path)
    image = Image.open(image_path).convert("RGB")
    tensor = preprocessing()(image).unsqueeze(0)
    with torch.no_grad():
        probabilities = torch.softmax(model(tensor), dim=1)[0]
    index = int(probabilities.argmax())
    return {"label": CLASSES[index], "confidence": float(probabilities[index])}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="staff_classifier.pth")
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    print(predict(args.model, args.image))


if __name__ == "__main__":
    main()
