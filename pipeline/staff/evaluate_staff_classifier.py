import argparse

from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder

from pipeline.staff.model import load_checkpoint, preprocessing
from pipeline.staff.train_staff_classifier import evaluate_loader


def evaluate(data_dir: str, model_path: str) -> dict:
    dataset = ImageFolder(data_dir, transform=preprocessing())
    loader = DataLoader(dataset, batch_size=16, shuffle=False)
    model = load_checkpoint(model_path)
    return evaluate_loader(model, loader)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--model", default="staff_classifier.pth")
    args = parser.parse_args()
    print(evaluate(args.data_dir, args.model))


if __name__ == "__main__":
    main()
