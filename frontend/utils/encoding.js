// App 逻辑层和部分小程序没有 TextEncoder。按 UTF-8 编码，保持旧网页密码哈希兼容。
export function utf8Bytes(value) {
  const bytes = []
  for (const char of value) {
    let point = char.codePointAt(0)
    if (point >= 0xd800 && point <= 0xdfff) point = 0xfffd
    if (point < 0x80) bytes.push(point)
    else if (point < 0x800) bytes.push(0xc0 | (point >> 6), 0x80 | (point & 0x3f))
    else if (point < 0x10000) bytes.push(0xe0 | (point >> 12), 0x80 | ((point >> 6) & 0x3f), 0x80 | (point & 0x3f))
    else bytes.push(0xf0 | (point >> 18), 0x80 | ((point >> 12) & 0x3f), 0x80 | ((point >> 6) & 0x3f), 0x80 | (point & 0x3f))
  }
  return Uint8Array.from(bytes)
}
