"""Lab 3.2 decoder architecture for loading its checkpoint in inference labs."""

import math

import torch
from torch import nn


class TinyDecoder(nn.Module):
    def __init__(self, vocab_size, context_length, width):
        super().__init__()
        self.token = nn.Embedding(vocab_size, width)
        self.position = nn.Embedding(context_length, width)
        self.norm1 = nn.LayerNorm(width)
        self.qkv = nn.Linear(width, 3 * width)
        self.attn_out = nn.Linear(width, width)
        self.norm2 = nn.LayerNorm(width)
        self.ff = nn.Sequential(nn.Linear(width, 2 * width), nn.GELU(), nn.Linear(2 * width, width))
        self.readout = nn.Sequential(nn.LayerNorm(width), nn.Linear(width, vocab_size))

    def forward(self, tokens):
        length = tokens.size(1)
        x = self.token(tokens) + self.position(torch.arange(length))
        q, k, v = self.qkv(self.norm1(x)).chunk(3, dim=-1)
        scores = q @ k.transpose(-1, -2) / math.sqrt(k.size(-1))
        future = torch.ones(length, length, dtype=torch.bool).triu(1)
        weights = scores.masked_fill(future, -torch.inf).softmax(-1)
        x = x + self.attn_out(weights @ v)
        x = x + self.ff(self.norm2(x))
        return self.readout(x)
