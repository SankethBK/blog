"""A small GPT-2-shaped decoder, shared by the architecture and training labs."""
import math

import torch
from torch import nn


class Attention(nn.Module):
    def __init__(self, width, heads):
        super().__init__()
        assert width % heads == 0
        self.heads = heads
        self.c_attn = nn.Linear(width, 3 * width)
        self.c_proj = nn.Linear(width, width)

    def forward(self, x):
        batch, length, width = x.shape
        q, k, v = (t.reshape(batch, length, self.heads, width // self.heads).transpose(1, 2)
                   for t in self.c_attn(x).chunk(3, dim=-1))
        scores = q @ k.transpose(-1, -2) / math.sqrt(q.size(-1))
        future = torch.ones(length, length, device=x.device, dtype=torch.bool).triu(1)
        mixed = scores.masked_fill(future, -torch.inf).softmax(-1) @ v
        return self.c_proj(mixed.transpose(1, 2).reshape(batch, length, width))


class MLP(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.c_fc = nn.Linear(width, 4 * width)
        self.c_proj = nn.Linear(4 * width, width)

    def forward(self, x):
        return self.c_proj(nn.functional.gelu(self.c_fc(x), approximate="tanh"))


class Block(nn.Module):
    def __init__(self, width, heads):
        super().__init__()
        self.ln_1 = nn.LayerNorm(width)
        self.attn = Attention(width, heads)
        self.ln_2 = nn.LayerNorm(width)
        self.mlp = MLP(width)

    def forward(self, x):
        x = x + self.attn(self.ln_1(x))
        return x + self.mlp(self.ln_2(x))


class GPT(nn.Module):
    def __init__(self, vocab, context, width, heads, layers):
        super().__init__()
        self.wte = nn.Embedding(vocab, width)
        self.wpe = nn.Embedding(context, width)
        self.h = nn.ModuleList(Block(width, heads) for _ in range(layers))
        self.ln_f = nn.LayerNorm(width)

    def forward(self, ids):
        x = self.wte(ids) + self.wpe(torch.arange(ids.size(1), device=ids.device))
        for block in self.h:
            x = block(x)
        return nn.functional.linear(self.ln_f(x), self.wte.weight)
