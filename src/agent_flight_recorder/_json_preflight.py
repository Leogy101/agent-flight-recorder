"""Bound JSON decoding work before constructing an untrusted OTLP document.

This conservative lexical pass is not a JSON parser. It counts string and
primitive tokens, object keys included, plus container boundaries, commas and
colons. It limits 500,000 such tokens, 100,000 members/elements in any container,
and 20 container levels. JSON syntax and semantic checks still follow. Escaped
string contents do not count as structure. Input is UTF-8, with an optional BOM.
"""

from .recording import MAX_CONTAINER_ITEMS, MAX_DEPTH, MAX_FILE_BYTES

MAX_JSON_TOKENS = 500_000
_WHITESPACE = " \t\r\n"
_DELIMITERS = '{}[],:" \t\r\n'


def preflight_json(raw: bytes) -> str:
    """Return decoded text only after checking work bounds without a token list."""
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("JSON input size limit exceeded")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError("OTLP JSON input must be UTF-8") from None
    # Each frame is [closing delimiter, item count, awaiting next item]. Its
    # memory is bounded by depth; no arrays of source tokens/items are created.
    stack = []
    tokens = 0
    index = 0
    length = len(text)

    def begin_item():
        if stack and stack[-1][2]:
            frame = stack[-1]
            frame[1] += 1
            if frame[1] > MAX_CONTAINER_ITEMS:
                raise ValueError("JSON container item limit exceeded before decoding")
            frame[2] = False

    while index < length:
        char = text[index]
        if char in _WHITESPACE:
            index += 1
            continue
        tokens += 1
        if tokens > MAX_JSON_TOKENS:
            raise ValueError("JSON token limit exceeded before decoding")
        if char == '"':
            begin_item()
            index += 1
            while index < length:
                char = text[index]
                if char == "\\":
                    index += 2
                elif char == '"':
                    index += 1
                    break
                else:
                    index += 1
            else:
                raise ValueError("Unterminated JSON string")
            continue
        if char in "{[":
            begin_item()
            if len(stack) >= MAX_DEPTH:
                raise ValueError("JSON nesting limit exceeded before decoding")
            stack.append(["}" if char == "{" else "]", 0, True])
        elif char in "}]":
            if not stack or stack[-1][0] != char:
                raise ValueError("Invalid JSON container structure")
            stack.pop()
        elif char == ",":
            if stack:
                stack[-1][2] = True
        elif char != ":":
            begin_item()
            # Skip one primitive token; json.loads validates its contents later.
            index += 1
            while index < length and text[index] not in _DELIMITERS:
                index += 1
            continue
        index += 1
    if stack:
        raise ValueError("Incomplete JSON container structure")
    return text
