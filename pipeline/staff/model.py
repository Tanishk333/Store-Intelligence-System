from pathlib import Path

import torch
from torch import nn
from torchvision import models, transforms


CLASSES = ["customer", "staff"]


def build_model() -> nn.Module:
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)
    for parameter in model.features.parameters():
        parameter.requires_grad = False
    model.classifier[1] = nn.Linear(model.last_channel, len(CLASSES))
    return model


def preprocessing():
    return transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )


def save_checkpoint(model: nn.Module, path: str | Path, metrics: dict | None = None) -> None:
    torch.save({"state_dict": model.state_dict(), "classes": CLASSES, "metrics": metrics or {}}, path)


def load_checkpoint(path: str | Path) -> nn.Module:
    model = build_model()
    checkpoint = torch.load(path, map_location="cpu")
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model
