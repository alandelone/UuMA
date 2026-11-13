from collections import Counter
from pathlib import Path
from uuma.librarian_read import LibrarianReader

archive_path = Path("/home/alandelone/.local/share/uuma/production/librarian/semantic-archive")
reader = LibrarianReader(archive_path, "librarian")

print(f"Total records in reader: {len(reader.records)}")
cats = Counter(r.category for r in reader.records.values())
print("Category distribution in live catalog:")
for cat, cnt in cats.most_common():
    print(f"  - {cat}: {cnt}")

projects = Counter(r.project_ids[0] if r.project_ids else "unassigned" for r in reader.records.values())
print("Project distribution in live catalog:")
for p, cnt in projects.most_common():
    print(f"  - {p}: {cnt}")
