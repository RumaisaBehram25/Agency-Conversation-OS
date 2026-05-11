import psycopg2

conn = psycopg2.connect("postgresql://attora:Attora-123@attora-db.cp8ooqrtonyo.us-east-1.rds.amazonaws.com:5432/attora")
cur = conn.cursor()
cur.execute("SELECT LEFT(conversion_playbook, 150) FROM ai_config WHERE org_id = '88351387-8882-49e0-a976-d5ef477a6309'")
text = cur.fetchone()[0]

print("Type:", type(text))
print("First 150 chars repr:", repr(text[:150]))
print()

# Check for replacement chars (U+FFFD = encoding failure)
bad = [(i, ch) for i, ch in enumerate(text) if ord(ch) > 127]
if bad:
    for i, ch in bad[:20]:
        print(f"pos {i}: {ch!r} = U+{ord(ch):04X}")
else:
    print("All ASCII — no high codepoints found")

# Also verify ESCALATION section is present
cur.execute("SELECT conversion_playbook FROM ai_config WHERE org_id = '88351387-8882-49e0-a976-d5ef477a6309'")
full = cur.fetchone()[0]
checks = [
    "ESCALATION & SALES CALL LOGIC",
    "Antidepressants or mood stabilizers",
    "POST-PURCHASE ESCALATION TO CALL",
    "[CALL_LINK]",
]
print()
print("=== Content checks ===")
for phrase in checks:
    found = phrase in full
    print(f"  {'OK' if found else 'MISSING'}: {phrase!r}")

cur.close()
conn.close()
