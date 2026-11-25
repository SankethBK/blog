---
title: "Continuous Batching — Who Gets the Next GPU Iteration?"
date: 2026-11-24T00:00:00+05:30
categories: ["ml"]
tags: ["ml", "inference", "serving", "continuous-batching", "transformers"]
---

# Continuous Batching — Who Gets the Next GPU Iteration?

The [speculative decoding note]({{< relref "posts/ml/2026-11-21-6-speculative-decoding-verifying-several-tokens-in-parallel.markdown" >}}) left one request making progress on a GPU while other requests waited outside. Suppose your GPU has room to serve two requests together. One finishes its answer in the next iteration. The other needs three more. When can you use the freed capacity to start a third conversation?

## 1. Watch a slot sit empty

Call the active requests A and B. Both have finished prefill and are ready to decode. C is waiting with a one-token prompt. For this example, each ordinary decode iteration consumes the most recently chosen token for each active request and emits one new token. A needs one more output token, B needs four, and C will finish after two. You know those lengths because you're looking at a completed trace. The server discovers them as it runs.

Compare two schedules. In both, the server streams a token as soon as it is ready. A star marks the iteration that emits the final token of a request. C's prefill produces its first output token.

```text
iteration             1       2       3       4       5       6
fixed batch
    first slot        A*      .       .       .       C       C*
    second slot       B       B       B       B*      .       .

continuous batch
    first slot        A*      C       C*      .
    second slot       B       B       B       B*
```

Look at iteration 2 of the fixed batch. A's client already has the answer. B is making progress. The person losing time is C's client. The fixed policy holds membership until the whole batch completes, so C gets its first token in iteration 5. If you allow the scheduler to choose a fresh membership at each boundary, C gets its first token in iteration 2. B still gets four decode steps.

That boundary is the mechanism called **iteration-level scheduling** in Orca. A “slot” in the drawing is permission to participate in a pass. Actual GPU time per pass depends on the work you admit. Counting six iterations versus four tells you the schedule. Measuring their durations tells you the speedup. [Orca paper](https://www.usenix.org/conference/osdi22/presentation/yu)

## 2. What exactly can two conversations share?

Follow iteration 3 of the continuous schedule. C and B each supply one new token. Let $d$ be the model width. Stack their hidden rows into $X$ of shape $(2,d)$. For one attention head of width $h$, the shared query projection $W_Q$ has shape $(d,h)$. One matrix multiply $XW_Q$ produces queries of shape $(2,h)$. The same model weights do useful work for both conversations.

Now stop at attention. Let $s_C$ and $s_B$ be the visible lengths after appending the current keys and values. For request $r$, meaning either C or B, its query $q_r$ has shape $(1,h)$, its keys $K_r$ and values $V_r$ each have shape $(s_r,h)$. The score row $q_rK_r^\top$ has shape $(1,s_r)$. After scaling and softmax over those $s_r$ positions, multiplying by $V_r$ gives an output of shape $(1,h)$. Stack the two outputs and you're back at $(2,h)$.

Suppose C can see 2 positions and B can see 103. C's softmax has **two** entries. Letting it attend to B's keys would change the answer to C's question. An implementation can pad and mask rows or pass separate sequence boundaries to an attention kernel. Either way, the request ID identifies the cache and the next position. The row number is only where you put that request in *this* pass.

## 3. Give C a long prompt

Change just one detail. C now arrives with 800 prompt tokens. The [KV-cache note]({{< relref "posts/ml/2026-11-10-4-kv-cache-making-autoregressive-generation-practical.markdown" >}}) established why prefill can process a known prompt in parallel. Parallel work still takes time. If the scheduler runs all of C's prompt alongside B's next token, B's client may see a conspicuous gap in the middle of a sentence.

A **token budget** caps the number of new input positions scheduled in one iteration. Suppose the budget is 128 and you reserve one position for B's decode. You can prefill up to 127 positions of C. Save their keys and values and continue with the next chunk at the next boundary. C can emit its first answer token after you process the last prompt position. B gets opportunities to advance between chunks. This is the idea behind *chunked prefill*, a trail to follow when you want to study scheduling policies. A token budget alone cannot predict iteration time because the cost also depends on how much history each query attends to.

## 4. Put a clock on the tradeoff

**Time to first token** measures arrival to first emitted token, including queueing and prefill. **Inter-token latency** measures the time between successive emitted tokens for one request. **Output throughput** counts all emitted output tokens divided by elapsed wall time. You can improve one while worsening another.

For example, suppose C arrived at time zero. Iteration 1 ends at 10 ms. A single long mixed iteration ends at 50 ms and emits C's first token and B's second. C's time to first token is 50 ms. B's gap is 40 ms. Now suppose two smaller mixed iterations end at 33 and 56 ms and together finish C's prefill. C waits 56 ms, while B sees gaps of 23 ms and 23 ms, provided it is still decoding. These are hypothetical timings. Which schedule would you choose for an interactive product that promises smooth streaming?

## 5. Pause theory and try the schedule

**Suggested lab exercise — a three-request scheduler on paper or in Python.** Replay the diagram with fixed iteration durations, log the emission time for each token, and recover all three metrics from the log. Then give prefill its own cost and vary the chunk size. Can you produce a trace where throughput improves while one client waits longer?

## 6. What comes next

A has finished. The scheduler has room to admit C. **Does the GPU actually have room for C's keys and values?** Answering that requires knowing where A's cache lived, which memory can be reused, and how B can keep growing. Follow the same requests into [PagedAttention]({{< relref "posts/ml/2026-11-24-8-paged-attention.markdown" >}}).
