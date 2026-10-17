"""How does the Exa provider actually resolve EXA_API_KEY?

It calls launchEnvironmentOf(ctx).get("EXA_API_KEY")?.value
So the question is: what does the launch environment read from?
  - OS environment variables?
  - the credentials store (.credentials.yaml refs)?
  - a config section?
This determines exactly how the user adds the key.
"""
import os
import re

ROOTS = [
    r"C:\Users\preet\.dsh\profiles\desktop\node_modules",
    r"C:\Users\preet\AppData\Local\Programs\DeepSeek Harness\resources\app.asar",
]

print("=" * 88)
print("A. Is @deepseek-ai/dsh-launch-environment installed locally?")
print("=" * 88)
local = os.path.join(ROOTS[0], "@deepseek-ai", "dsh-launch-environment")
if os.path.isdir(local):
    for dirpath, dirnames, filenames in os.walk(local):
        for name in filenames:
            if name.endswith(".js"):
                print("  ", os.path.join(dirpath, name).replace(local, "dsh-launch-environment"))
else:
    print("  not in the profile node_modules (ships inside app.asar)")

print()
print("=" * 88)
print("B. launchEnvironmentOf — where do values come from?")
print("=" * 88)
asar = ROOTS[1]
with open(asar, "rb") as handle:
    text = handle.read().decode("utf-8", errors="ignore")

for needle in ("launchEnvironmentOf", "LaunchEnvironment", "launchEnvironment"):
    hits = list(re.finditer(re.escape(needle), text))
    print(f"\n  '{needle}' appears {len(hits)} times")
    for match in hits[:2]:
        start = max(0, match.start() - 250)
        snippet = re.sub(r"\s+", " ", text[start:match.end() + 450])
        print(f"     ...{snippet[:600]}...")

print()
print("=" * 88)
print("C. Does it read process.env, or the credentials domain?")
print("=" * 88)
for pattern in (r"process\.env\[[^\]]{0,40}\]", r"credentials[\.\[]", r"fromEnv", r"environmentVariables"):
    found = sorted(set(re.findall(pattern, text)))
    if found:
        print(f"  {pattern:<30} {found[:5]}")
