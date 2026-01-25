def prost(n):
    if n < 2:
        return 0
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return 0
    return 1

def dl(n):
    mach = 0
    man = 0
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            if i % 2 == 0 and i > mach:
                mach = i
            if i % 2 != 0 and i > man:
                man = i
            if n//i % 2 == 0 and n//i > mach:
                mach = n//i
            if n//i % 2 != 0 and n//i > man:
                man = n//i
    if mach == 0 or man == 0:
        return 0
    return abs(mach - man)

k = 0
for n in range(250_0157, 10 ** 10):
    a = dl(n)
    if prost(a) == 1 and a % 10 == 9:
        print(n, a)
        k += 1
        if k == 5:
            break

