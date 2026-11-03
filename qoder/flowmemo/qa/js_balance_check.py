import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()


def strip(s):
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            while i < n and s[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and s[i + 1] == "*":
            i += 2
            while i + 1 < n and not (s[i] == "*" and s[i + 1] == "/"):
                i += 1
            i += 2
        elif c in ("'", '"'):
            q = c
            i += 1
            while i < n:
                if s[i] == "\\":
                    i += 2
                    continue
                if s[i] == q:
                    i += 1
                    break
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


body = strip(src)
ok = True
for a, b in (("{", "}"), ("(", ")"), ("[", "]")):
    ca, cb = body.count(a), body.count(b)
    print("%s%s  open=%d close=%d %s" % (a, b, ca, cb, "BALANCED" if ca == cb else "MISMATCH"))
    ok = ok and ca == cb
print("BOM:", open(path, "rb").read(3) == b"\xef\xbb\xbf")
print("addDiagnostic tokens:", src.count("addDiagnostic"))
print("RESULT:", "PASS" if ok else "FAIL")
