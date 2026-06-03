import argparse
from pathlib import Path

import torch
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score, recall_score
from torch import nn
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder

from pipeline.staff.model import build_model, preprocessing, save_checkpoint


def train(data_dir: str, output: str, epochs: int = 5, batch_size: int = 16, lr: float = 1e-3) -> dict:
    dataset = ImageFolder(data_dir, transform=preprocessing())
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    model = build_model()
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.classifier.parameters(), lr=lr)
    model.train()

    for _ in range(epochs):
        for images, labels in loader:
            optimizer.zero_grad()
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()

    metrics = evaluate_loader(model, loader)
    Path(output).parent.mkdir(parents=True, exist_ok=True) if Path(output).parent != Path(".") else None
    save_checkpoint(model, output, metrics)
    return metrics


def evaluate_loader(model, loader) -> dict:
    y_true, y_pred = [], []
    model.eval()
    with torch.no_grad():
        for images, labels in loader:
            preds = model(images).argmax(dim=1)
            y_true.extend(labels.tolist())
            y_pred.extend(preds.tolist())
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, average="macro", zero_division=0),
        "recall": recall_score(y_true, y_pred, average="macro", zero_division=0),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output", default="staff_classifier.pth")
    parser.add_argument("--epochs", type=int, default=5)
    args = parser.parse_args()
    print(train(args.data_dir, args.output, args.epochs))


if __name__ == "__main__":
    main()
