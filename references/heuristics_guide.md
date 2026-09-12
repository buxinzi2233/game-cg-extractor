# 生僻与未知游戏封包启发式逆向指南

当目标封包未命中 `references/recipes.json`，且通过 `search_web` 也未能找到社区现成的 QuickBMS 脚本或开源工具时，请按本指南进行自主推导。

---

## 阶段一：二进制结构嗅探与统计分析

运行 `python3 scripts/probe_archive.py "<file>"`，检查输出：

1. **香农熵（Shannon Entropy）分析**：
   - **熵值 < 4.0**：明文非压缩数据，大概率包含未压缩的索引表、明文路径列表。
   - **4.0 <= 熵值 <= 7.0**：轻度压缩或带有格式头的打包数据。
   - **7.0 < 熵值 <= 8.0**：高度压缩（zlib/lz4/zstd）或高强度加密（AES/XOR）。
2. **内嵌图片签名扫描**：
   - 检查整个文件中是否包含常见格式的 Magic Bytes：
     - **PNG**: `89 50 4E 47 0D 0A 1A 0A`
     - **JPEG**: `FF D8 FF`
     - **WEBP**: `52 49 46 46` ... `57 45 42 50`
     - **Ogg**: `4F 67 67 53`
   - 若发现上述签名且数量较多，说明文件为**非加密的归档聚合包**（直接根据偏移量和长度即可精准切分提取出原图）。

---

## 阶段二：常见封包架构逆向思路

大部分自研小众引擎采用以下三种架构之一：

### 架构 A：头索引表型 (Header-Indexed Archive)
- **结构**：
  ```text
  [Magic (4B)] [FileCount (4B)] [IndexTableOffset (4B)] ...
  IndexTable:
    [FileName (null-terminated or length-prefixed)]
    [Offset (4B/8B)]
    [CompressedSize (4B)]
    [DecompressedSize (4B)]
  ```
- **逆向方法**：
  - 读取前 16 字节，查看是否存在代表文件总数或索引表偏移的无符号小端整数（uint32_le）。
  - 跳转到索引表位置，观察是否为文件名列表。

### 架构 B：尾索引表型 (Tail-Indexed Archive)
- **结构**：
  ```text
  [Payload 1] [Payload 2] ... [IndexTable] [TableSize (4B)] [Magic (4B)]
  ```
- **逆向方法**：
  - 检查文件末尾 16~64 字节，常常存储着索引表相对文件头的偏移指针或大小。

### 架构 C：内嵌压缩块流 (Chunked Compressed Stream)
- 常见压缩流标记：
  - **ZLIB / DEFLATE**: `78 9C` (默认), `78 DA` (最高压缩), `78 01` (无压缩)
  - **LZ4**: `04 22 4D 18`
  - **ZSTD**: `28 B5 2F FD`
- **逆向方法**：
  - 使用纯 Python 标准库 `zlib.decompressobj()` 或 `offzip` 从标志偏移处尝试解压。

---

## 阶段三：常见混淆/简易异或（XOR）破解技巧

许多日系小游戏不采用复杂加密算法，而是使用简单的固定字节异或（Single-byte XOR）或多字节循环异或（Key Cycle XOR）。

### 已知明文攻击法 (Known-Plaintext XOR Attack)
假设封包内部第一张图是 PNG 格式，PNG 的前 8 字节永远是固定的：
`P = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]`

若密文前 8 字节为 `C`，则异或密钥 `K` 可以直接推导：
`K[i] = C[i] ^ P[i]`

1. 若 `K[0] == K[1] == ... == K[7]`，则说明是**单字节 XOR 加密**！只需对全文件每个字节异或 `K[0]` 即可瞬间还原全文件。
2. 若 `K` 呈现 4 字节或 8 字节周期重复，则说明是对应长度的循环 Key。

---

## 阶段四：验证与自进化回写

- 一旦通过以上方法试探出解包脚本或参数，并在工作区成功提取出图像。
- 必须立刻运行 `scripts/filter_and_sort.py` 与 `scripts/sample_verifier.py` 验证抽样真实有效性。
- 验证通过后，将此格式的特征、逻辑或脚本加入 `references/recipes.json`，完成经验进化。
