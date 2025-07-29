---
title:  "Processor Modes in x86"
date:   2025-06-18
draft: true
categories: ["cpu"]
tags: ["cpu", "x86"]
author: Sanketh
references:
    - title:  Virtual Memory in the x86 
      url: https://www.youtube.com/watch?v=jkGZDb3100Q

    - title:  How a Single Bit Inside Your Processor Shields Your Operating System's Integrity 
      url: https://www.youtube.com/watch?v=H4SDPLiUnv4
---

# The 8086 Processor

## A Brief History

The Intel 8086, released in 1978, marked a pivotal moment in computing history as Intel's first 16-bit microprocessor. Designed by a team led by Stephen Morse, the 8086 was Intel's answer to the growing demand for more powerful processors that could handle larger programs and address more memory than the existing 8-bit chips of the era.

The processor introduced the x86 architecture that would become the foundation for decades of computing evolution. With its 16-bit registers and 20-bit address bus [^address-bus], the 8086 could access up to 1 megabyte of memory—a massive improvement over the 64KB limitation of 8-bit processors. However, it retained backward compatibility concepts that would prove both beneficial and constraining for future generations.

### Why 20-bit Address Bus in the 8086?

The 8086 used a 20-bit address bus, which was a deliberate design decision based on several factors:

- **Memory Capacity:** With 20 address lines, the processor could address 2^20 = 1,048,576 locations, or exactly 1 megabyte of memory. In 1978, this was considered enormous - most computers had only 4KB to 64KB of memory.

- **Economic Considerations:** Adding more address lines would have increased the chip's pin count, making it more expensive to manufacture and requiring more expensive motherboards. Intel balanced capability with cost-effectiveness.

## The Segmented Memory Model

Intel's previous 8-bit processors contained 8-bit wide registers and 16-bit wide address bus, which can enable addressing of 2^16 = 64KB of memory. So thoeretically a program could use 64KB of memory. 

Intel's main goal was to maintain programming familiarity while expanding addressable memory. They wanted programmers to continue thinking in terms of 16-bit addresses (which they were already comfortable with from 8-bit processors) while secretly accessing a larger memory space. The segmentation model essentially says: "You can still write programs using 16-bit addresses, but we'll automatically map these into different 64KB 'segments' of the larger 1MB space."

The physical address was divided into 2 parts: selector/segment and offset. 
- **Selector (Segment):** 16-bit value stored in one of CS, DS, ES, SS, etc.
- **Offset:** 16-bit value (e.g., in SI, DI, BP, SP, or an immediate/displacement).
- **Physical Address Calculation:** physical_address = (selector × 16) + offset

The idea is to express a 20-bit address using 2 16-bit registers. A selector register (CS, DS, ES, SS) indicates the starting address of the segment and the offset register (SI, DI, BP, SP) indicates the boundary of the segment. Since the offset is 16-bits, the boundary can be at a maximum of 64KB thus maintaining backward compatibility.

```
     20-bit physical address space   (1 MB total)
     ─────────────────────────────────────────────────────────
     00000h                                                      FFFFFh
        ↑                                                         ↑
        │                                                         │
        │<────────── 64 KB window (Segment N) ───────────>│
        │                                                 │
        │          │<────────── 64 KB window (Segment N+1) ───────────>│
        │          │                                      │
        │          └───────────  overlap  ────────----────┘
        │
   base = N × 16 bytes                base = (N+1) × 16 bytes
   address = (segment × 16) + offset  address = (segment × 16) + offset
```

**What the diagram shows**

1.  A *segment* is not a fixed block—it’s a **sliding 64 KB window** that can start on **any 16-byte paragraph**.  
    *Segment value = paragraph number; multiplying by 16 shifts the window left or right in 16-byte steps.*
    
2.  **Segment N** and **Segment N+1** start only 16 bytes apart, so their two 64 KB windows overlap almost completely.  
    Any physical byte inside that overlap can be reached with two (or many more) different *segment:offset* pairs.
    
3.  Because the window can slide to **65,536** different paragraph positions (0000h–FFFFh), the segment register must be **16 bits** wide—not just 4 bits.
    
4.  The **offset** (0–65m535) always selects the byte inside the current 64 KB window.  
    Together, *segment* and *offset* build the 20-bit physical address:


### Disadvantages of the Segmentation Model

1.  **64 KB Segment Limit:**

    - Each selector covers only 64 KB (the 16-bit offset range). Although it was theoretically possible to support a higher offset which means larger segment memory for a program.
    - Large programs or data structures must be split across multiple segments.
    - Switching segments (e.g., changing CS or DS) adds overhead and complexity.
        
2.  **Alias Addresses:**
    
    - The same physical byte can be addressed by many segment:offset pairs.     
    - Example: physical 04808₁₆ = 047C:0048 = 047D:0038 = 047E:0028 = 047B:0058     
    - Makes comparing or normalizing pointers tricky.

### The Real Mode




[^address-bus]: An address bus is a collection of wires (or electrical pathways) that carries memory addresses from the processor to memory and other components. Think of it as the "postal system" of the computer - when the CPU wants to read from or write to a specific location in memory, it sends that location's address through the address bus. Each wire in the address bus represents one bit of the address. The CPU sets each wire to either high voltage (representing binary 1) or low voltage (representing binary 0) to form the complete binary address.