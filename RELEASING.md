# Releasing

This repository hosts **two** add-ons (`voice-match`, `wyoming-openai-stt`) that version
independently, but ships **one combined GitHub Release** per release event.

## How it works

`.github/workflows/release.yml` triggers on tag push and builds a single release body
containing both add-ons' changelog sections:

- It reads the pushed tag as the release version.
- It pulls the matching `## <version>` section from `voice-match/CHANGELOG.md`.
- It pulls the matching `## <version>` section from `wyoming-openai-stt/CHANGELOG.md`
  — if that add-on's version didn't change, its own **latest** section is used instead
  (so the release still shows its current changelog, not nothing).

## How to cut a release

1. Bump whichever add-on(s) changed: `config.yaml` `version:` + a new `## X.Y.Z` entry
   at the top of that add-on's `CHANGELOG.md`.
2. Commit and push to `main`.
3. Push **exactly one** git tag, matching the version you want as the release title
   (normally the `voice-match` version, since it's the primary add-on):

   ```bash
   git tag 3.0.1
   git push origin 3.0.1
   ```

4. The `Release` workflow creates one GitHub Release automatically.

## What NOT to do

- **Do not** push a second tag for the other add-on (e.g. `wyoming-openai-stt-2.0.1`)
  to "cover" it — the workflow already includes both add-ons in the one release from
  step 3. A second tag only produces a duplicate, empty release.
- **Do not** run `gh release create` by hand. It bypasses the changelog-assembly logic
  above and produces an empty title/body.

If a duplicate/empty release ever slips through, delete both the release and its tag:

```bash
gh release delete <tag> --yes
git push origin :refs/tags/<tag>
```
