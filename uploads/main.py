s = input()
k = 0
w = 0
n = len(s)
i = 0

while i < n:
    c = s[i]

    # Проверка на букву
    letter = 0
    if c in "qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM":
        letter = 1

    if letter == 1:
        w = 1
    elif c == '-':
        # Проверяем левую сторону
        left_letter = 0
        if i > 0:
            lc = s[i - 1]
            if lc in "qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM":
                left_letter = 1

        # Проверяем правую сторону
        right_letter = 0
        if i < n - 1:
            rc = s[i + 1]
            if rc in "qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM":
                right_letter = 1

        if left_letter == 1 and right_letter == 1:
            w = 1
        else:
            if w == 1:
                k += 1
                w = 0
    else:
        if w == 1:
            k += 1
            w = 0
    i += 1

if w == 1:
    k += 1

print(k)