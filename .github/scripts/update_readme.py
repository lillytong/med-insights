import subprocess
import os
import anthropic

README_PATH = "README.md"


def get_diff():
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "HEAD", "--", "*.py", "*.yml", "*.json"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def read_readme():
    with open(README_PATH, "r") as f:
        return f.read()


def write_readme(content):
    with open(README_PATH, "w") as f:
        f.write(content)


def main():
    diff = get_diff()
    if not diff:
        print("No relevant code changes detected. Skipping README update.")
        return

    print(f"Diff length: {len(diff)} chars")
    current_readme = read_readme()

    client = anthropic.Anthropic()
    prompt = f"""You are maintaining the README for a GitHub repository.

Here is the current README:
<readme>
{current_readme}
</readme>

Here is the git diff of the latest commit:
<diff>
{diff}
</diff>

Analyze the diff and decide:
- If the changes are significant (new features, changed behavior, renamed files, updated schedule, new dependencies, structural changes) → return a fully updated README reflecting the changes. Keep the same tone, format and structure. Only update what actually changed.
- If the changes are minor (bug fixes, logging tweaks, refactoring with no behavioral change) → respond with exactly: NO_UPDATE

Respond with either the full updated README content, or NO_UPDATE. Nothing else."""

    print("Calling Claude Sonnet to analyze changes...")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    response = message.content[0].text.strip()

    if response == "NO_UPDATE":
        print("Claude determined no README update needed.")
        return

    print("Claude updated the README.")
    write_readme(response)


if __name__ == "__main__":
    main()
