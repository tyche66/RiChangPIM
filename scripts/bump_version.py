import pathlib
root = pathlib.Path("/home/AI-PIM/RiChangPIM")
for f in ["frontend/package.json", "backend/app/core/config.py"]:
    p = root / f
    t = p.read_text()
    t = t.replace("1.9.2", "1.9.3")
    p.write_text(t)
    print(f"updated {f}")
