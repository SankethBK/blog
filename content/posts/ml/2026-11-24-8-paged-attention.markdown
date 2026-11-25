---
title: "PagedAttention — Where Does the Next Token's Cache Go?"
date: 2026-11-24T00:01:00+05:30
categories: ["ml"]
tags: ["ml", "inference", "kv-cache", "paged-attention", "serving"]
---

# PagedAttention — Where Does the Next Token's Cache Go?

The [continuous batching note]({{< relref "posts/ml/2026-11-24-7-continuous-batching.markdown" >}}) ended with A finishing and C waiting to enter. You can remove A from the batch immediately. Can C use the memory A just released even if B sits in the middle of the cache pool?

## 1. Count the space and then try to use it

Imagine a GPU cache with room for 24 token positions. Each position stands for all the key and value storage one token needs across the model. To keep the addresses readable, group the drawing into six blocks of four positions. Before A finishes, A occupies the first eight positions, B the next eight, and the final eight are free.

```text
physical block       0      1      2      3      4      5
before A finishes   AAAA   AAAA   BBBB   BBBB   ....   ....
after A finishes    ....   ....   BBBB   BBBB   ....   ....
```

C has a ten-token prompt. You can count sixteen free positions, yet the longest free run has length eight. A policy requiring one contiguous allocation for C must move data, wait, or choose another placement strategy. This is **external fragmentation**. The gaps are usable individually but their locations prevent this allocation. Reserving room for each request's maximum possible length up front creates another cost: you set aside space that other requests could use while the answer is still short.

## 2. Give C a logical address space

With paging, C owns a sequence of **logical blocks** numbered from zero. A block table records the physical block that currently backs each logical block. As with virtual memory, adjacent logical addresses can live far apart. Here the entries locate KV tensors on the GPU.

Give C physical blocks 0, 1 and 4. Keep B's existing blocks in place. Dots inside C's final block are slots reserved for its next tokens.

```text
C logical block       0      1      2
C physical block      0      1      4

physical block        0      1      2      3      4      5
contents             CCCC   CCCC   BBBB   BBBB   CC..   ....
C token indices      0..3   4..7                 8,9
```

Let $b$ be the block size in tokens, $t$ a zero-based position in C, and $P_C$ its one-dimensional block table, here of shape $(3,)$. The logical block index is $j=\lfloor t/b\rfloor$ and the offset within it is $o=t\bmod b$. The physical address is the pair $(P_C[j],o)$. For $t=9$ and $b=4$, the answer is physical block 4, offset 1. C's position in the model is still 9. Feeding 4 or 1 to the positional encoding would quietly change the model you're running.

Follow the next three writes. Positions 10 and 11 fit in block 4. Position 12 needs a new block, so you can append physical block 5 to C's table. If B had taken block 5 first, C would now have to wait or the scheduler would have to reclaim space. Count free blocks again at growth boundaries, even for requests already admitted.

## 3. How does a query read scattered keys?

Take one layer and one head. Let $h$ be the head width. In this example the key pool and the value pool each have logical storage shape $(6,4,h)$, indexed by physical block, offset and feature. A particular implementation can arrange the memory axes differently. C's ten valid positions define a logical key matrix $K_C$ and value matrix $V_C$, each of shape $(10,h)$.

For a query $q$ of shape $(1,h)$, the three page reads produce score pieces of shapes $(1,4)$, $(1,4)$ and $(1,2)$. There are only two valid values in that last piece. All ten scores must compete in **one softmax**. Normalizing each piece independently would give each physical block its own unit of probability mass.

You can see how a kernel can combine blocks without copying C's full history into a contiguous buffer. Call the scaled score of logical token $i$ the scalar $s_i=qk_i^\top/\sqrt h$, where its key $k_i$ and value $v_i$ each have shape $(1,h)$. Choose a common shift $m=\max_i s_i$. For each block, sum $\exp(s_i-m)v_i$ over valid tokens to obtain a numerator of shape $(1,h)$. Sum $\exp(s_i-m)$ over those same tokens to obtain a scalar denominator. Add the three numerators, add the three denominators, then divide once. You recover the ordinary attention output of shape $(1,h)$. This describes the arithmetic, independent of how a kernel tiles or parallelizes it. [PagedAttention paper](https://arxiv.org/abs/2309.06180)

## 4. What does one block cost?

Let $L$ be the number of layers, $H$ the number of KV heads per layer, and $e$ the bytes per cached scalar. With equal key and value widths $h$, a full model-wide block costs $2LbHhe$ bytes. The factor two pays for keys and values. For $L=12$, $H=12$, $h=64$, $e=2$ and $b=4$, that is 147,456 bytes, or 144 KiB. Two unused positions in C's last block temporarily cost 72 KiB.

This is **internal fragmentation**. C can grow into those positions, but another independent request cannot use them while C owns the block. Smaller blocks reduce the possible waste in a final block and require more table entries for the same context. A separate breadcrumb is **prefix sharing**: requests with identical cached prefixes can refer to the same immutable blocks. Releasing a shared block requires tracking its remaining owners. [PagedAttention paper](https://arxiv.org/abs/2309.06180)

## 5. Pause theory and try the allocator

**Suggested lab exercise — paged versus contiguous attention.** Use the six-block layout and four-token blocks above. Put conspicuously large values into C's unused slots. Compare the paged read with ordinary attention over C's ten valid rows. Why should the output agree even after you permute the physical blocks and update the table? What error would including those two unused slots reveal?

## 6. Back to training

Through the inference series you've changed how a model executes while keeping its learned weights fixed. Return to the [training note]({{< relref "posts/ml/2026-09-20-3-training-a-language-model-end-to-end.markdown" >}}), where backprop supplied a gradient for every weight. **Once a gradient arrives, what state does the optimizer keep, and how does it decide how far that weight moves?** Follow one coordinate through [two AdamW updates]({{< relref "posts/ml/2026-11-24-9-adamw.markdown" >}}).
