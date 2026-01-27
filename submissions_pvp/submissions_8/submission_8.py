
sp1 = list(map(int, input().split()))
n = sp1[0]
sp = sp1[1:]
s = 0
for e in sp:
    if sp.count(e) == 1:
        s += e
print(s)