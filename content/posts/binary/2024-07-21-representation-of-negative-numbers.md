---
title: "Representation of Negative Numbers in Hardware"
date: 2024-07-21
draft: false
tags: ["binary"]
categories: ["cpu"]
references:
   - title: Why Inversion and Adding One Works (Cornell)
     url: https://www.cs.cornell.edu/~tomf/notes/cps104/twoscomp.html 
   - title: Why Two's Complement Makes Addition and Subtraction Simple (Stackoverflow)
     url: https://stackoverflow.com/a/1125317/10553747
   - title: Negative numbers in binary (Ben Eater)
     url: https://www.youtube.com/watch?v=4qH4unVtJkE
   - title: Binary Plusses & Minuses (Computerphile)
     url: https://www.youtube.com/watch?v=lKTsv6iVxV4
   - title: Ones' complement (Wikipedia)
     url: https://en.wikipedia.org/wiki/Ones%27_complement
   - title: Two's complement (Wikipedia)
     url: https://en.wikipedia.org/wiki/Two%27s_complement
   - title: Offset binary (Wikipedia)
     url: https://en.wikipedia.org/wiki/Offset_binary
---


Representing negative numbers in binary poses unique challenges due to the inherent nature of binary systems. Unlike decimal systems, which can easily use a minus sign to indicate negative values, binary systems must encode this information within a fixed number of bits. This requirement leads to various methods of representation, each with its own set of advantages and limitations. The main challenge lies in developing a system that can accurately represent both positive and negative values while ensuring that arithmetic operations remain efficient and straightforward. In the following sections, we will explore several common approaches to representing negative numbers in binary, including their respective challenges and trade-offs.

## Characteristics of an Ideal Representation

1. **Simple Arithmetic Operations:** The representation should simplify the implementation of basic arithmetic operations (addition, subtraction, multiplication, and division) without needing special handling for positive and negative numbers in electronic circuits.
2. **Single Representation for Zero:** There should be only one binary representation for zero to avoid ambiguity and simplify comparison operations.
3. **Symmetry:** The range of representable positive and negative numbers should be symmetric around zero, meaning that the total number of positive and negative values should be as close as possible if not the same.
4. **Overflow Detection:** The representation should allow for easy detection of overflow conditions during arithmetic operations.
5. **Bitwise Consistency:** The representation should be consistent with bitwise logical operations such as AND, OR, and NOT, ensuring that these operations work correctly without special cases for negative numbers.
6. **Ease of Conversion:** The method for converting between positive and negative representations should be simple and intuitive.
7. **Sign Interpretation:** The responsibility for interpreting whether an operand is positive or negative should lie with the compiler, not the CPU. This ensures that the CPU does not need to perform additional checks during instruction decode and execution phase.
8. **Unambiguous Interpretation:** The representation should ensure that arithmetic operations yield correct results whether a number starting with 1 is interpreted as a negative number or as a large unsigned positive number. For example, in C, `1001` can be interpreted as `-7` in signed integers and `9` in unsigned integers. Since the CPU does not inherently know whether a number is positive or negative, the arithmetic results should be consistent and correct under both interpretations.

## Common Methods for Representing Negative Numbers

1. Sign and Magnitude
2. One's Complement
3. Two's Complement
4. Excess-N (Offset Binary)


### 1. Sign and Magnitude

The most common approach is using a reserved sign bit to indicate whether a binary number is positive or negative and the remaining bits represent the magnitude (absolute value) of the number. In sign and magnitude, the Most Signinificant Bit (MSB) is reserved as sign-bit. A `0` in the MSB indicates a positive number and `1` indicates negative number, 


**Range of Representation**

For an n-bit number, the range of representable values is 
$$ -(2^{(n-1)} - 1) \text{ to } 2^{(n-1)} - 1 $$

If we consider a 4-bit system, these are all the possible representations

| Binary Representation | Decimal Value |
| --------------------- | ------------- |
| 1111                  | -7            |
| 1110                  | -6            |
| 1101                  | -5            |
| 1100                  | -4            |
| 1011                  | -3            |
| 1010                  | -2            |
| 1001                  | -1            |
| 1000                  | -0            |
| 0000                  | 0             |
| 0001                  | 1             |
| 0010                  | 2             |
| 0011                  | 3             |
| 0100                  | 4             |
| 0101                  | 5             |
| 0110                  | 6             |
| 0111                  | 7             |



**Pros**

- Easy to understand and visualize since the sign and magnitude are separated.
- Converting from positive to negative is simple: just flip the MSB.

**Cons**

- **Complex Arithmetic Operations:** Addition and subtraction require special handling of the sign bit, making the implementation of these operations more complex in hardware. Adder circuits used for adding positive numbers cannot be used directly for operations involving mixed signs. For eg: `add 5 (-2)` will result in `-7` (`0101` + `1010` = `1111`) which is not correct.  To handle such cases correctly, the CPU must first check the most significant bit (MSB) of both operands to determine their signs. It must then use a separate circuit to handle subtraction. This will cause performance overhead as CPU can no longer just rely on opcode for determining the type of operation but also the sign of operands. 

- **Dual Zero Representations:** Sign and magnitude representation has two different representations for zero: positive zero (`0000`) and negative zero (`1000`). This redundancy complicates the design of comparison operations. For example, checking for zero requires additional logic to account for both representations, and ensuring consistent behavior across arithmetic operations becomes more challenging. Having two representations for zeros also introduces error in airthemtic operations. 

- **Lack of Support for Unsigned Integers:** In sign and magnitude representation, the most significant bit (MSB) is always reserved for the sign bit. This means the CPU relies on the MSB along with the opcode to determine the operation. As a result, we can't have support for unsigned integers, because a large unsigned integer starting with `1` will be mistakenly interpreted as a negative number by the CPU. This limitation makes it difficult to handle a mix of signed and unsigned data in the same system efficiently.


### 2. One's Complement 

In One's Complement system, positive numbers are represented the same way as in standard binary, while negative numbers are represented by inverting all the bits of the corresponding positive number (flipping all 0s to 1s and all 1s to 0s). For instance, in an 8-bit system, the number +5 is represented as `00000101`, and -5 is represented as `11111010`. 

**Range of Representation**

For an n-bit number, the range of representable values is 
$$ -(2^{(n-1)} - 1) \text{ to } 2^{(n-1)} - 1 $$

| Binary Representation | Decimal Value |
| --------------------- | ------------- |
| 1000                  | -7            |
| 1001                  | -6            |
| 1010                  | -5            |
| 1011                  | -4            |
| 1100                  | -3            |
| 1101                  | -2            |
| 1110                  | -1            |
| 1111                  | -0            |
| 0000                  | 0             |
| 0001                  | 1             |
| 0010                  | 2             |
| 0011                  | 3             |
| 0100                  | 4             |
| 0101                  | 5             |
| 0110                  | 6             |
| 0111                  | 7             |

**Adding 2 numbers**


Adding two values is straightforward. Simply align the values on the least significant bit and add, propagating any carry to the bit one position left. If the carry extends past the end of the word it is said to have "wrapped around", a condition called an "end-around carry". When this occurs, the bit must be added back in at the right-most bit. This phenomenon does not occur in two's complement arithmetic. The value of MSB has no special significance to the CPU.

```
   0111      7
+  1001     -6
=======   ====
 1|0000      1
      1
=======
   0001 
```


**Pros**

One's complement solves some of the problems of sign and magnitude approach, they are
  
- **Unified Adder Circuit:** Unlike the sign and magnitude representation, the same adder circuit can be used for both positive and negative numbers in one's complement. The primary modification needed is the addition of logic to handle end-around carry when an overflow occurs. This change is consistent across all cases, meaning there is no extra overhead for negative numbers specifically. 
- **Theoretical Support for Unsigned Integers:** Since the value of MSB has no special significance to CPU, it is theoretically possible to support unsigned integers. However, a genuine overflow can lead to incorrect results due to the wrap-around carry.

**Cons**

One's complement retains the issue of dual zero representations from the sign and magnitude approach. The reason one's complement performs wrap-around carry is to compensate for the shift in one digit along the number line caused by the presence of negative zero. This introduces an additional step in arithmetic operations to handle this anomaly, slightly complicating the overall design.

### 3. Two's complement

Two's complement is the most widely used method for representing signed integers in binary systems. Two's complement of a number is calculated by flipping the bits and adding `1` to the Least Significant Bit (LSB).

**Range of Representation**

For an n-bit number, the range of representable values is 
$$ -2^{(n-1)} \text{ to } 2^{(n-1)} - 1 $$

| Binary Representation | Decimal Value (signed) | Decimal Value (unsigned) |
| --------------------- | ---------------------- | ------------------------ |
| 1000                  | -8                     | 8                        |
| 1001                  | -7                     | 9                        |
| 1010                  | -6                     | 10                       |
| 1011                  | -5                     | 11                       |
| 1100                  | -4                     | 12                       |
| 1101                  | -3                     | 13                       |
| 1110                  | -2                     | 14                       |
| 1111                  | -1                     | 15                       |
| 0000                  | 0                      | 0                        |
| 0001                  | 1                      | 1                        |
| 0010                  | 2                      | 2                        |
| 0011                  | 3                      | 3                        |
| 0100                  | 4                      | 4                        |
| 0101                  | 5                      | 5                        |
| 0110                  | 6                      | 6                        |
| 0111                  | 7                      | 7                        |


**Intuition Behind Two's Complement**

In one's complement approach we saw that whenever a negative number is involved in addition the result could generate a carry which we have to wrap around to get correct answer. The reason for this is whenever result falls on positive side of the number line it has to cross two zero's. Because of this, the result will fall short by one number on the number line. Two's complement solves this by adding `1` to the one's complement of a number which effectively removes `-0` from the binary number line threby giving correct result.

Sum of any n-bit number and its one's complement gives the highest possible number that can be represented by those n-bits. For eg:

```
 0010 (2 in 4 bit system)
+1101 (1's complement of 2)
___________________________
 1111  (the highest number that we can represent with 4 bits)
```

`1111` is `-0` in one's complement. Now what will happen if we try to add `1` more to the result. It will results in an overflow.

The result will be `10000` which is `0`. Because we ignore the overflow bit in two's complement. 

So the statement can be generalized as 

```
Any n-bit number + its one's complement = max n-bit number
Any n-bit number + its one's complement + 1 = 0
```

Adding `1` to the one's complement itself is called as two's complement as it involves one more additional step to one's complement. So the statement can also be written as

```
Any n-bit number + its two's complement = 0
```

The rationale behind two's complement can be understood by comparing it with the unsigned binary interpretation:

Taking an 8-bit value a<sub>7</sub> a<sub>6</sub> a<sub>5</sub> a<sub>4</sub> a<sub>3</sub> a<sub>2</sub> a<sub>1</sub> a<sub>0</sub>

The usual unsigned binary interpretation is:

$$ 2^7 \cdot a_7 + 2^6 \cdot a_6 + 2^5 \cdot a_5 + 2^4 \cdot a_4 + 2^3 \cdot a_3 + 2^2 \cdot a_2 + 2^1 \cdot a_1 + 2^0 \cdot a_0 $$

```
11111111 = 128 + 64 + 32 + 16 + 8 + 4 + 2 + 1 = 255
```

In the two's complement representation, all negative numbers have the MSB set to 1. To get the negative number represented by the two's complement of a value, we need to multiply the MSB with -1. The formula for two's complement is:

$$ -2^7 \cdot a_7 + 2^6 \cdot a_6 + 2^5 \cdot a_5 + 2^4 \cdot a_4 + 2^3 \cdot a_3 + 2^2 \cdot a_2 + 2^1 \cdot a_1 + 2^0 \cdot a_0 $$

For eg: negative number represented by `11111111` is 

```
11111111 = -128 + 64 + 32 + 16 + 8 + 4 + 2 + 1 = -1
```

It's important to note that while `11111111` represents `-1` in the signed two's complement system, it can also be interpreted as `255` in unsigned integers, as the CPU does not enforce any restriction. The interpretation is determined by the compiler.

**Pros**

Two's complement solves all the limitations from sign and magnitude and one's complement representations:

1. **Single Representation for Zero:** In two's complement, zero has only one unique representation. This eliminates the problem of having two distinct representations for zero, which was a limitation in the one's complement system. By having a single, consistent zero, two's complement simplifies arithmetic operations and avoids the issue of shifting results by one number.

2. **Natural Support for Unsigned Integers:** Since MSB has no special significance and there is no change in the process of addition (unlike wrap around carry in one's complement). Two's complement naturally enables support for unsigned integers.

    ```c
    For example in C

    unsigned int a = 2;                             0010
    unsigned int b = 9;                            +1001
    unsigned int c = a + b; /* result is 11 */  ==  1011  

    int a = 2;                                      0010
    int b = -7;                                    +1001
    int c = a + b; /* result is -5 */           ==  1011
    ```

    We can see that even though result is `1011` in both cases. Compiler interprets it as `11` in the first case and `-5` in the second case. 

    In both cases, the binary result is `1011`. However, the interpretation differs based on whether the numbers are treated as unsigned or signed. The compiler interprets `1011` as `11` when dealing with unsigned integers and as `-5` for signed integers. This flexibility is possible because the CPU treats the binary numbers uniformly without needing special handling for the sign.

3. **Sign Extension in Two's Complement:** Two's complement numbers can be sign-extended to match the size of the storage medium while preserving their value. For example, consider the 4-bit representation `1110`, which corresponds to `-2`. To store this in a 32-bit register, we simply extend the MSB across the additional bits. The resulting 32-bit representation would be `1111 1111 1111 1111 1111 1111 1111 1110`. This extension ensures that the value `-2` is maintained accurately in arithmetic operations, regardless of the bit width of the register.

### 3. Excess-N (Offset Binary) Representation

In excess-N notation, a fixed value, called the bias or offset (N), is added to the actual integer value to form the encoded value. This approach shifts the range of representable numbers, ensuring that all encoded values are non-negative. The value of bias K is usually choosen as 2<sup>n-1</sup> so that the representation is symmetric around 0. For example, with a bias = 3, the number -3 would be represented as 0, 0 would be represented as 3 and 3 would be represented as 6 and so on. 

This representation simplifies certain types of arithmetic operations and is particularly useful in applications such as floating-point arithmetic and digital signal processing. Excess-N encoding simplifies comparison and subtraction operations, as the encoded values can be compared directly without considering the sign. This representation is widely used in the exponent field of IEEE 754 floating-point numbers, where it helps manage the range of representable exponents efficiently.

| Binary Representation | Decimal Value (Excess-8) | Decimal Value (Unsigned) |
| --------------------- | ------------------------ | ------------------------ |
| 0000                  | -8                       | 0                        |
| 0001                  | -7                       | 1                        |
| 0010                  | -6                       | 2                        |
| 0011                  | -5                       | 3                        |
| 0100                  | -4                       | 4                        |
| 0101                  | -3                       | 5                        |
| 0110                  | -2                       | 6                        |
| 0111                  | -1                       | 7                        |
| 1000                  | 0                        | 8                        |
| 1001                  | 1                        | 9                        |
| 1010                  | 2                        | 10                       |
| 1011                  | 3                        | 11                       |
| 1100                  | 4                        | 12                       |
| 1101                  | 5                        | 13                       |
| 1110                  | 6                        | 14                       |
| 1111                  | 7                        | 15                       |

**Range of Representation**

For an n-bit number with bias as K, range of representation can be given by 
$$ -k \text{ to } (2^n - 1) - k.$$
