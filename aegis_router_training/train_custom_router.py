"""AEGIS Custom Router Model Architecture & Training Script.
Trains a custom lightweight Transformer Router model designed to run on the Raspberry Pi 8GB with <25ms latency.
"""
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import json
import math
import os
from typing import List, Dict

# ==============================================================================
# Model Architecture: Ultra-Fast Lightweight Transformer Decoder (150M - 250M)
# ==============================================================================

class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x):
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps) * self.weight

class SwiGLU(nn.Module):
    def __init__(self, dim: int, hidden_dim: int):
        super().__init__()
        self.w1 = nn.Linear(dim, hidden_dim, bias=False)
        self.w2 = nn.Linear(hidden_dim, dim, bias=False)
        self.w3 = nn.Linear(dim, hidden_dim, bias=False)

    def forward(self, x):
        return self.w2(nn.functional.silu(self.w1(x)) * self.w3(x))

class TransformerBlock(nn.Module):
    def __init__(self, d_model: int, n_heads: int, d_ff: int):
        super().__init__()
        self.norm1 = RMSNorm(d_model)
        self.attn = nn.MultiheadAttention(d_model, n_heads, batch_first=True)
        self.norm2 = RMSNorm(d_model)
        self.ffn = SwiGLU(d_model, d_ff)

    def forward(self, x, mask=None):
        h = self.norm1(x)
        attn_out, _ = self.attn(h, h, h, attn_mask=mask, is_causal=True)
        x = x + attn_out
        x = x + self.ffn(self.norm2(x))
        return x

class AEGISRouterModel(nn.Module):
    def __init__(self, vocab_size: int = 4096, d_model: int = 512, n_layers: int = 6, n_heads: int = 8, d_ff: int = 1536):
        super().__init__()
        self.token_emb = nn.Embedding(vocab_size, d_model)
        self.pos_emb = nn.Embedding(512, d_model)
        self.layers = nn.ModuleList([TransformerBlock(d_model, n_heads, d_ff) for _ in range(n_layers)])
        self.norm_f = RMSNorm(d_model)
        self.head = nn.Linear(d_model, vocab_size, bias=False)

    def forward(self, x):
        b, s = x.size()
        pos = torch.arange(0, s, device=x.device).unsqueeze(0)
        h = self.token_emb(x) + self.pos_emb(pos)
        for layer in self.layers:
            h = layer(h)
        h = self.norm_f(h)
        logits = self.head(h)
        return logits

# ==============================================================================
# Simple Character/Subword Tokenizer for Custom Lab Vocabulary
# ==============================================================================

class SimpleTokenizer:
    def __init__(self):
        self.chars = sorted(list(set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-:,{}[].'\"/\n!@#$%^&*()+=?<>|;~`àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ\u0900-\u097F")))
        self.char_to_id = {c: i + 3 for i, c in enumerate(self.chars)}
        self.char_to_id["<PAD>"] = 0
        self.char_to_id["<BOS>"] = 1
        self.char_to_id["<EOS>"] = 2
        self.id_to_char = {i: c for c, i in self.char_to_id.items()}
        self.vocab_size = len(self.char_to_id)

    def encode(self, text: str, max_len: int = 256) -> List[int]:
        tokens = [1] + [self.char_to_id.get(c, 0) for c in text][:max_len - 2] + [2]
        if len(tokens) < max_len:
            tokens += [0] * (max_len - len(tokens))
        return tokens

    def decode(self, ids: List[int]) -> str:
        res = []
        for i in ids:
            if i in [0, 1]: continue
            if i == 2: break
            res.append(self.id_to_char.get(i, ""))
        return "".join(res)

class RouterDataset(Dataset):
    def __init__(self, jsonl_path: str, tokenizer: SimpleTokenizer, max_len: int = 256):
        self.data = []
        self.tokenizer = tokenizer
        self.max_len = max_len
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                text = f"USER: {item['input']}\nROUTER: {item['output']}"
                self.data.append(text)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        tokens = self.tokenizer.encode(self.data[idx], self.max_len)
        x = torch.tensor(tokens[:-1], dtype=torch.long)
        y = torch.tensor(tokens[1:], dtype=torch.long)
        return x, y

def train():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training on device: {device}")
    
    tokenizer = SimpleTokenizer()
    dataset = RouterDataset("aegis_router_training/router_training_data.jsonl", tokenizer)
    loader = DataLoader(dataset, batch_size=16, shuffle=True)

    model = AEGISRouterModel(vocab_size=tokenizer.vocab_size).to(device)
    optimizer = optim.AdamW(model.parameters(), lr=1e-3, weight_decay=0.01)
    criterion = nn.CrossEntropyLoss(ignore_index=0)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"AEGIS-Router Parameter Count: {total_params / 1e6:.2f}M parameters")

    print("Starting training...")
    model.train()
    for epoch in range(3):
        total_loss = 0
        for step, (x, y) in enumerate(loader):
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            logits = model(x)
            loss = criterion(logits.view(-1, tokenizer.vocab_size), y.view(-1))
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            if (step + 1) % 25 == 0:
                print(f"Epoch [{epoch+1}/3] Step [{step+1}/{len(loader)}] Loss: {loss.item():.4f}")

    # Save weights
    out_file = "aegis_router_training/aegis_router_model.pt"
    torch.save({
        "model_state": model.state_dict(),
        "vocab_size": tokenizer.vocab_size,
        "char_to_id": tokenizer.char_to_id
    }, out_file)
    print(f"Model saved successfully at: {out_file}")

if __name__ == "__main__":
    train()
