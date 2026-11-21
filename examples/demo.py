"""Five-line tour of phi-guard.  Run: python examples/demo.py"""

from pathlib import Path

from phi_guard import Guard, Redactor, analyze

here = Path(__file__).parent
note = (here / "sample_note.txt").read_text(encoding="utf-8")

redactor = Redactor(key="demo-key-not-secret")
result = redactor.redact(note)
print(result.text)
print("Counts:", result.counts())
print("Restored matches original:", redactor.restore(result.text) == note)

report = analyze((here / "poisoned_doc.txt").read_text(encoding="utf-8"))
print(f"Poisoned document: {report.verdict} (score {report.score:.2f}) rules={report.rules}")

guard = Guard(redactor)
clean = (here / "clean_policy.txt").read_text(encoding="utf-8")
print("Clean policy allowed:", guard.inspect(clean, untrusted=True).allowed)
