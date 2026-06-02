import torch
print(f"CUDA disponible: {torch.cuda.is_available()}")
print(f"Dispositivo: {'GPU' if torch.cuda.is_available() else 'CPU'}")