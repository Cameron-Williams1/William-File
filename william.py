import zipfile, os

i = 0
while True:
    with zipfile.ZipFile(f"william_{i}.zip", "w") as z:
        z.writestr("william.txt", "William")
    i += 1
