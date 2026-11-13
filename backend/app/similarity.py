"""Image similarity for duplicate detection.

- Defect-level: DINOv2 ViT-S/14 384-d global embedding of the defect crop, compared with cosine similarity.
- Upload-level: 64-bit difference hash (dHash) of the whole frame to catch the exact same photo uploaded twice.
"""
import threading

import cv2
import numpy as np

_lock = threading.Lock()
_net = None
_tf = None
_dev = "cpu"
_kind = None


def _load():
    """DINOv2 ViT-S/14 (self-supervised, strong for instance retrieval); ResNet18 fallback if unavailable.

    Calibrated on RDD2022-India crops (same defect under crop shift / scale / brightness / blur vs other defects):
    DINOv2 cos>=0.80 -> TPR 0.87 at FPR 0.0045; ResNet18 needed 0.88 for TPR 0.70 at FPR 0.0055.
    """
    global _net, _tf, _dev, _kind
    with _lock:
        if _net is None:
            import torch
            from torchvision import transforms as T
            _dev = "cuda" if torch.cuda.is_available() else "cpu"
            try:
                net = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14", verbose=False)
                _kind = "dinov2_vits14"
            except Exception:
                import torchvision
                net = torchvision.models.resnet18(weights=torchvision.models.ResNet18_Weights.IMAGENET1K_V1)
                net.fc = torch.nn.Identity()
                _kind = "resnet18"
            _net = net.eval().to(_dev)
            _tf = T.Compose([T.ToPILImage(), T.Resize((224, 224)), T.ToTensor(),
                             T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    return _net, _tf


def embed(bgr) -> np.ndarray:
    import torch
    net, tf = _load()
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    with torch.no_grad():
        v = net(tf(rgb).unsqueeze(0).to(_dev)).squeeze(0).float().cpu().numpy()
    v = v / (np.linalg.norm(v) + 1e-9)
    return v.astype(np.float32)


def to_bytes(v: np.ndarray) -> bytes:
    return v.astype(np.float32).tobytes()


def from_bytes(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)


def cosine(a, b) -> float:
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9))


def dhash(bgr, size=8) -> str:
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return "%016x" % int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")
